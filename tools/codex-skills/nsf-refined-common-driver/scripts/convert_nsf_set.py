"""Generic CLI for the verified NSF-to-refined-common-driver converter.

The heavy conversion and validation logic lives in ``converter_core.py``. This
wrapper supplies a reusable, conservative input boundary and optional manifest
without weakening the original 三目童子 profile.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import converter_core as core


def parse_offset(value: Any) -> int:
    if isinstance(value, int):
        offset = value
    elif isinstance(value, str):
        text = value.strip().replace("$", "0x", 1)
        offset = int(text, 0)
    else:
        raise TypeError(f"driver offset must be an integer or string: {value!r}")
    if not 0 <= offset < 0x1000:
        raise ValueError(f"driver offset outside 4 KiB page: {value!r}")
    return offset


def validate_generic_nsf(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) < 0x80 or raw[:5] != b"NESM\x1a":
        raise ValueError(f"not an NSF file: {path}")
    if raw[6] != 1:
        raise ValueError(
            f"{path.name}: expected one song per NSF, header declares {raw[6]}"
        )
    if raw[0x7B] != 0:
        raise ValueError(
            f"{path.name}: expansion-audio flags ${raw[0x7B]:02X} are unsupported"
        )
    region = raw[0x7A] & 0x03
    if region == 1:
        raise ValueError(f"{path.name}: PAL-only NSF is unsupported")
    load = raw[8] | raw[9] << 8
    init = raw[10] | raw[11] << 8
    play = raw[12] | raw[13] << 8
    if not load or not init or not play:
        raise ValueError(
            f"{path.name}: invalid LOAD/INIT/PLAY ${load:04X}/${init:04X}/${play:04X}"
        )
    return {
        "file": str(path),
        "bytes": len(raw),
        "sha256": core.sha256_bytes(raw),
        "load": f"${load:04X}",
        "init": f"${init:04X}",
        "play": f"${play:04X}",
        "banked": any(raw[0x70:0x78]),
        "region": "dual" if region == 2 else "ntsc",
    }


def validate_reference(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) < core.DRIVER_SLICE.stop:
        raise ValueError(f"reference NSF is too small: {path}")
    if raw[:5] != b"NESM\x1a":
        raise ValueError(f"reference is not an NSF: {path}")
    if raw[8:14] != core.EXPECTED_ENTRY:
        raise ValueError(
            "reference NSF must use LOAD/INIT/PLAY $F000/$F100/$F160"
        )
    if raw[0x70:0x78] != core.EXPECTED_BANK_INIT:
        raise ValueError(
            "reference NSF must use initial banks 01 02 03 04 05 06 07 00"
        )
    return raw


def load_manifest(path: Path | None) -> tuple[dict[str, Any], Path | None]:
    if path is None:
        return {}, None
    resolved = path.resolve()
    data = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("manifest root must be a JSON object")
    return data, resolved.parent


def read_dpcm_samples(
    value: Any, manifest_dir: Path | None
) -> dict[str, bytes]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("dpcmSamples must be an object")
    samples: dict[str, bytes] = {}
    for name, source in value.items():
        if not isinstance(source, dict):
            raise ValueError(f"DPCM sample {name!r} must be an object")
        choices = {key for key in ("file", "hex") if key in source}
        if len(choices) != 1:
            raise ValueError(
                f"DPCM sample {name!r} must contain exactly one of file or hex"
            )
        if "file" in source:
            sample_path = Path(str(source["file"]))
            if not sample_path.is_absolute():
                if manifest_dir is None:
                    raise ValueError("relative DPCM path requires a manifest")
                sample_path = manifest_dir / sample_path
            data = sample_path.resolve().read_bytes()
        else:
            data = bytes.fromhex(str(source["hex"]))
        samples[str(name)] = data
    return samples


def collect_tracks(
    input_dir: Path,
    manifest: dict[str, Any],
    glob_pattern: str,
) -> list[dict[str, Any]]:
    configured = manifest.get("tracks")
    if configured is None:
        paths = sorted(input_dir.glob(glob_pattern))
        return [{"file": path.name, "path": path} for path in paths]
    if not isinstance(configured, list) or not configured:
        raise ValueError("manifest tracks must be a non-empty array")
    tracks: list[dict[str, Any]] = []
    for item in configured:
        if not isinstance(item, dict) or not item.get("file"):
            raise ValueError("each manifest track needs a file")
        path = Path(str(item["file"]))
        if not path.is_absolute():
            path = input_dir / path
        copied = dict(item)
        copied["path"] = path.resolve()
        tracks.append(copied)
    return tracks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert compatible one-song 2A03 NSF files to an exact "
            "$F000/$F100/$F160 refined common driver."
        )
    )
    parser.add_argument("--profile", choices=("generic", "mitsume"), default="generic")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--glob", default="*.nsf")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reference-nsf", type=Path, required=True)
    parser.add_argument("--famistudio", type=Path, required=True)
    parser.add_argument("--pydeps", type=Path)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--output-prefix", default="Converted")
    parser.add_argument(
        "--project-name", default="NES NSF - refined common driver"
    )
    parser.add_argument(
        "--preserve-driver-offset",
        action="append",
        default=[],
        help="offset inside the 4 KiB driver page; repeat as needed",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.max_seconds <= 0:
        raise ValueError("--max-seconds must be positive")

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"input directory not found: {input_dir}")
    famistudio = args.famistudio.resolve()
    if not famistudio.is_file():
        raise FileNotFoundError(f"FamiStudio not found: {famistudio}")
    manifest, manifest_dir = load_manifest(args.manifest)
    tracks = collect_tracks(input_dir, manifest, args.glob)
    if not tracks:
        raise ValueError(f"no NSF files selected in {input_dir}")

    paths = [Path(track["path"]) for track in tracks]
    if len(set(paths)) != len(paths):
        raise ValueError("the same NSF file was selected more than once")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"source NSF not found: {path}")

    if args.profile == "mitsume":
        if args.manifest:
            raise ValueError("mitsume profile uses the complete directory; omit --manifest")
        source_set: dict[str, object] = core.validate_source_set(sorted(paths))
        tracks = [{"file": path.name, "path": path} for path in sorted(paths)]
    else:
        source_set = {
            "profile": "generic",
            "files": [validate_generic_nsf(path) for path in paths],
        }

    reference_path = args.reference_nsf.resolve()
    reference = validate_reference(reference_path)
    mpu_class, _ = core.load_py65(args.pydeps)
    build_dir = args.build_dir.resolve()
    assets_dir = args.assets_dir.resolve()
    dist_dir = args.dist_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    manifest_offsets = manifest.get("preserveDriverOffsets", [])
    if not isinstance(manifest_offsets, list):
        raise ValueError("preserveDriverOffsets must be an array")
    global_offsets = {
        parse_offset(value)
        for value in list(args.preserve_driver_offset) + manifest_offsets
    }
    default_prefix = str(manifest.get("outputPrefix", args.output_prefix))
    project_name = str(manifest.get("projectName", args.project_name))

    records: list[dict[str, object]] = []
    for track in tracks:
        track_offset_values = track.get("preserveDriverOffsets", [])
        if not isinstance(track_offset_values, list):
            raise ValueError("track preserveDriverOffsets must be an array")
        track_offsets = global_offsets | {
            parse_offset(value) for value in track_offset_values
        }
        records.append(
            core.convert_one(
                Path(track["path"]),
                famistudio=famistudio,
                reference=reference,
                build_dir=build_dir,
                assets_dir=assets_dir,
                dist_dir=dist_dir,
                mpu_class=mpu_class,
                max_frames=args.max_seconds * 60,
                title_override=track.get("title"),
                project_name=project_name,
                output_prefix=str(track.get("outputPrefix", default_prefix)),
                source_selector_offset=0x3831 if args.profile == "mitsume" else None,
                preserve_driver_offsets=tuple(sorted(track_offsets)),
                dpcm_sample_data_overrides=read_dpcm_samples(
                    track.get("dpcmSamples"), manifest_dir
                ),
            )
        )

    report = {
        "format": "NES NSF to refined F000/F100/F160 common driver v1",
        "profile": args.profile,
        "sourceSet": source_set,
        "referenceNsf": str(reference_path),
        "referenceNsfSha256": core.sha256_bytes(reference),
        "commonDriverSha256": core.sha256_bytes(reference[core.DRIVER_SLICE]),
        "famiStudio": str(famistudio),
        "tracks": records,
    }
    report_path = (
        args.report.resolve()
        if args.report
        else build_dir / "conversion_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
