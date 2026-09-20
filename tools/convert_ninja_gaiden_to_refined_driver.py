"""Convert Ninja Gaiden's ``The Dragon's Battlefield`` NSF to the common driver.

The source uses a banked, non-page-aligned $FC00 load image and two DPCM
samples.  The shared converter emulates the original mapping, captures the
audible 2A03 performance through FamiStudio, and validates both tonal channels
and DPCM triggers before accepting the exact ROM common driver page.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from convert_mitsume_to_refined_driver import (
    DEFAULT_REFERENCE,
    DRIVER_SLICE,
    EXPECTED_BANK_INIT,
    EXPECTED_ENTRY,
    convert_one,
    load_py65,
    sha256_bytes,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUILD = ROOT / "build" / "ninja_gaiden_refined"
DEFAULT_ASSETS = ROOT / "assets" / "music" / "03 忍者龙剑传（精修通用驱动）"
DEFAULT_DIST = ROOT / "dist" / "music" / "忍者龙剑传（精修通用驱动）"
SOURCE_ENTRY = bytes.fromhex("00 FC 40 C0 00 80")
SOURCE_BANK_INIT = bytes.fromhex("01 02 03 04 05 00 00 00")
TITLE = "鲜烈之龙（4-2）"


def validate_source(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:5] != b"NESM\x1a":
        raise ValueError(f"not an NSF: {path}")
    if raw[5] != 1 or raw[6] != 1 or raw[7] != 1:
        raise ValueError("expected the one-song NSF v1 source")
    if raw[8:14] != SOURCE_ENTRY:
        raise ValueError(
            "unexpected source entry points; expected load/init/play "
            "$FC00/$C040/$8000"
        )
    if raw[0x70:0x78] != SOURCE_BANK_INIT:
        raise ValueError("unexpected source bank initialization")
    if raw[0x7A] not in (0, 1) or raw[0x7B] != 0:
        raise ValueError("source is not a standard 2A03 NTSC/dual-region NSF")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Ninja Gaiden - The Dragon's Battlefield to the refined common driver."
    )
    parser.add_argument("--input-nsf", type=Path, required=True)
    parser.add_argument("--famistudio", type=Path)
    parser.add_argument("--pydeps", type=Path)
    parser.add_argument("--reference-nsf", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()

    source = args.input_nsf.resolve()
    source_raw = validate_source(source)
    music_root = source.parent.parent
    famistudio = (
        args.famistudio
        if args.famistudio is not None
        else music_root / ".tools" / "FamiStudio453" / "FamiStudio.exe"
    ).resolve()
    if not famistudio.is_file():
        raise FileNotFoundError(f"FamiStudio not found: {famistudio}")
    pydeps = args.pydeps
    if pydeps is None and (music_root / ".tools" / "pydeps").is_dir():
        pydeps = music_root / ".tools" / "pydeps"
    mpu_class, _ = load_py65(pydeps)

    reference_path = args.reference_nsf.resolve()
    reference = reference_path.read_bytes()
    if (
        reference[:5] != b"NESM\x1a"
        or reference[8:14] != EXPECTED_ENTRY
        or reference[0x70:0x78] != EXPECTED_BANK_INIT
    ):
        raise ValueError("reference NSF is not the accepted common-driver format")

    build_dir = args.build_dir.resolve()
    assets_dir = args.assets_dir.resolve()
    dist_dir = args.dist_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    record = convert_one(
        source,
        famistudio=famistudio,
        reference=reference,
        build_dir=build_dir,
        assets_dir=assets_dir,
        dist_dir=dist_dir,
        mpu_class=mpu_class,
        max_frames=args.max_seconds * 60,
        title_override=TITLE,
        project_name="Ninja Gaiden - refined common driver",
        output_prefix="忍者龙剑传",
        source_selector_offset=None,
        # These are per-export configuration bytes, not executable driver
        # code.  They select DPCM support/data placement and must match the
        # generated song image.  Every other byte comes from the accepted ROM
        # common-driver page.
        preserve_driver_offsets=(0x000, 0x003, 0x004),
        dpcm_sample_data_overrides={
            # Original DPCM ranges are $FC00-$FD00 and $FD00-$FF00.  They
            # overlap at $FD00 exactly as the source APU addressing does.
            "Sample 1": source_raw[0x80 : 0x80 + 0x101],
            "Sample 2": source_raw[0x80 + 0x100 : 0x80 + 0x100 + 0x201],
        },
    )
    report = {
        "format": "Ninja Gaiden to refined F000/F100/F160 common driver v1",
        "source": {
            "path": str(source),
            "bytes": len(source_raw),
            "sha256": sha256_bytes(source_raw),
            "loadInitPlay": ["$FC00", "$C040", "$8000"],
            "bankInit": SOURCE_BANK_INIT.hex(" ").upper(),
        },
        "referenceNsf": str(reference_path),
        "referenceNsfSha256": sha256_bytes(reference),
        "commonDriverSha256": sha256_bytes(reference[DRIVER_SLICE]),
        "famiStudio": str(famistudio),
        "tracks": [record],
    }
    report_path = (
        args.report.resolve()
        if args.report is not None
        else build_dir / "conversion_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
