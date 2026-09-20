"""Rebuild the softened Flapper Girl NSF with the ROM common driver.

FamiStudio's NSF importer records the softened driver's audible APU state as
per-frame channel-volume events.  Exporting that recording directly is too
large for Flapper Girl's single 8 KiB ROM data bank.  This tool folds those
events into deduplicated instrument volume envelopes before exporting, then
binds the repository's exact $F000/$F100/$F160 common driver page.

Inputs are read-only.  All intermediates and the candidate NSF are written to
``build/`` unless an explicit output directory is selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import convert_mitsume_to_refined_driver as common


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFERENCE = (
    ROOT
    / "assets"
    / "music"
    / "01 精修通用驱动（F000-F100-F160）"
    / "Flapper Girl - 琉妮精修.nsf"
)
DEFAULT_BUILD = ROOT / "build" / "flapper_rom_driver_soft_rebuild"
OUTPUT_NSF = "Flapper Girl - 琉妮精修（ROM同驱动柔和数据版）.nsf"
OUTPUT_PROJECT = "Flapper Girl - 琉妮精修（ROM同驱动柔和数据版）_FamiStudio.txt"
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def attributes(line: str) -> dict[str, str]:
    return dict(ATTR_RE.findall(line))


def render_note(attrs: dict[str, str]) -> str:
    return "\t\t\t\tNote " + " ".join(
        f'{key}="{value}"' for key, value in attrs.items()
    )


@dataclass
class Event:
    line_index: int
    pattern: str
    attrs: dict[str, str]
    absolute_time: int = 0


@dataclass
class Channel:
    name: str
    patterns: dict[str, list[Event]] = field(default_factory=dict)
    instances: dict[str, list[int]] = field(default_factory=dict)


def parse_channels(lines: list[str], pattern_frames: int) -> dict[str, Channel]:
    channels: dict[str, Channel] = {}
    channel: Channel | None = None
    pattern: str | None = None
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("Channel "):
            attrs = attributes(stripped)
            channel = Channel(attrs["Type"])
            channels[channel.name] = channel
            pattern = None
        elif channel is not None and stripped.startswith("Pattern Name="):
            pattern = attributes(stripped)["Name"]
            channel.patterns.setdefault(pattern, [])
        elif channel is not None and stripped.startswith("PatternInstance "):
            attrs = attributes(stripped)
            channel.instances.setdefault(attrs["Pattern"], []).append(
                int(attrs["Time"])
            )
            pattern = None
        elif (
            channel is not None
            and pattern is not None
            and stripped.startswith("Note ")
        ):
            channel.patterns[pattern].append(
                Event(line_index, pattern, attributes(stripped))
            )

    for channel in channels.values():
        for pattern_name, events in channel.patterns.items():
            uses = channel.instances.get(pattern_name, [])
            if not uses:
                continue
            if len(uses) != 1:
                raise ValueError(
                    f"recorded pattern is reused and cannot be compacted safely: "
                    f"{channel.name}/{pattern_name}/{uses}"
                )
            base = uses[0] * pattern_frames
            for event in events:
                event.absolute_time = base + int(event.attrs["Time"])
    return channels


def duty_for_instrument(name: str) -> int:
    match = re.fullmatch(r"Duty (\d+)", name)
    if not match:
        raise ValueError(f"unexpected recorded instrument: {name}")
    duty = int(match.group(1))
    if not 0 <= duty <= 3:
        raise ValueError(f"invalid duty cycle: {name}")
    return duty


def compact_recorded_project(source: Path, destination: Path) -> dict[str, object]:
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    song_line = next(line for line in lines if line.strip().startswith("Song "))
    song_attrs = attributes(song_line)
    pattern_frames = int(song_attrs["PatternLength"])
    total_frames = int(song_attrs["Length"]) * pattern_frames
    channels = parse_channels(lines, pattern_frames)

    replacements: dict[int, str | None] = {}
    instrument_by_signature: dict[tuple[int, tuple[int, ...]], str] = {}
    instrument_specs: list[tuple[str, int, tuple[int, ...]]] = []
    max_envelope = 0
    removed_volume_events = 0
    rewritten_notes = 0

    for channel_name in ("Square1", "Square2", "Noise"):
        channel = channels[channel_name]
        events = [
            event
            for pattern_events in channel.patterns.values()
            for event in pattern_events
            if channel.instances.get(event.pattern)
        ]
        events.sort(key=lambda event: (event.absolute_time, event.line_index))

        volume_changes: dict[int, int] = {}
        for event in events:
            if "Volume" in event.attrs:
                volume_changes[event.absolute_time] = int(event.attrs["Volume"])
        volumes: list[int] = []
        current_volume = 15
        for frame in range(total_frames):
            current_volume = volume_changes.get(frame, current_volume)
            volumes.append(current_volume)

        notes = [event for event in events if "Value" in event.attrs]
        for note_index, event in enumerate(notes):
            start = event.absolute_time
            duration = int(event.attrs.get("Duration", "1"))
            next_start = (
                notes[note_index + 1].absolute_time
                if note_index + 1 < len(notes)
                else total_frames
            )
            active_frames = max(1, min(duration, next_start - start, total_frames - start))
            envelope = list(volumes[start : start + active_frames])
            if not envelope:
                raise ValueError((channel_name, start, duration))
            while len(envelope) > 1 and envelope[-2] == envelope[-1]:
                envelope.pop()
            max_envelope = max(max_envelope, len(envelope))
            if len(envelope) > 255:
                raise ValueError(
                    f"volume envelope exceeds 255 frames: {channel_name} "
                    f"time={start} length={len(envelope)}"
                )

            duty = duty_for_instrument(event.attrs["Instrument"])
            signature = (duty, tuple(envelope))
            instrument_name = instrument_by_signature.get(signature)
            if instrument_name is None:
                instrument_name = f"ROM Soft {len(instrument_specs) + 1:03d}"
                instrument_by_signature[signature] = instrument_name
                instrument_specs.append((instrument_name, duty, tuple(envelope)))

            updated = dict(event.attrs)
            updated["Instrument"] = instrument_name
            updated.pop("Volume", None)
            replacements[event.line_index] = render_note(updated)
            rewritten_notes += 1

        for event in events:
            if "Value" in event.attrs or "Volume" not in event.attrs:
                continue
            updated = dict(event.attrs)
            updated.pop("Volume")
            if list(updated) == ["Time"]:
                replacements[event.line_index] = None
                removed_volume_events += 1
            else:
                replacements[event.line_index] = render_note(updated)

    instrument_lines: list[str] = []
    colors = ("5e35b1", "00897b", "f57c00", "7e57c2", "039be5", "43a047")
    for index, (name, duty, envelope) in enumerate(instrument_specs):
        instrument_lines.append(
            f'\tInstrument Name="{name}" Color="{colors[index % len(colors)]}"'
        )
        instrument_lines.append(
            f'\t\tEnvelope Type="Volume" Length="{len(envelope)}" '
            f'Values="{",".join(str(value) for value in envelope)}"'
        )
        if duty:
            instrument_lines.append(
                f'\t\tEnvelope Type="DutyCycle" Length="1" Values="{duty}"'
            )

    output: list[str] = []
    inserted = False
    for line_index, line in enumerate(lines):
        if not inserted and line.strip().startswith("Song "):
            output.extend(instrument_lines)
            inserted = True
        replacement = replacements.get(line_index, line)
        if replacement is not None:
            output.append(replacement)
    if not inserted:
        raise ValueError("song line not found")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")
    return {
        "patternFrames": pattern_frames,
        "totalFrames": total_frames,
        "instrumentsAdded": len(instrument_specs),
        "rewrittenNotes": rewritten_notes,
        "removedVolumeEvents": removed_volume_events,
        "maxEnvelopeFrames": max_envelope,
    }


def fidelity_passed(report: dict[str, object]) -> bool:
    pulse1 = report["pulse1"]
    pulse2 = report["pulse2"]
    triangle = report["triangle"]
    noise = report["noise"]
    dmc = report["dmc"]
    assert isinstance(pulse1, dict) and isinstance(pulse2, dict)
    assert isinstance(triangle, dict) and isinstance(noise, dict)
    assert isinstance(dmc, dict)
    for pulse in (pulse1, pulse2):
        if (
            pulse["onOffMismatchFrames"]
            or pulse["dutyMismatchAudibleFrames"]
            or pulse["meanAbsoluteVolumeError"]
            or pulse["pitchWithin25CentsPercent"] != 100.0
        ):
            return False
    return not (
        triangle["onOffMismatchFrames"]
        or triangle["pitchWithin25CentsPercent"] != 100.0
        or noise["onOffMismatchFrames"]
        or noise["meanAbsoluteVolumeError"]
        or noise["periodMismatchAudibleFrames"]
        or dmc["triggerMismatchFrames"]
    )


def choose_rotated_loop_timeline(
    loop: common.LoopInfo, skipped_frames: int
) -> tuple[int, int, int | None, int, int]:
    """Keep original leading silence and rotate a repeating loop if needed.

    The source loop length is 9 * 947 frames, but its earliest valid loop
    boundary is 28 frames before a 947-frame pattern boundary.  Recording 28
    frames into the already-repeating section gives an equivalent loop without
    delaying the start of the song.
    """
    if loop.loop_start is None or loop.loop_length is None:
        import_start, end, start, pattern_frames = common.choose_timeline(
            loop, skipped_frames
        )
        return import_start, end, start, pattern_frames, 0
    for shift in range(loop.loop_length):
        start = loop.loop_start + shift
        end = start + loop.loop_length
        try:
            pattern_frames = common.largest_common_pattern_frame(start, end)
        except RuntimeError:
            continue
        return skipped_frames, end, start, pattern_frames, shift
    raise RuntimeError("cannot place an equivalent rotated loop")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-nsf", type=Path, required=True)
    parser.add_argument("--famistudio", type=Path, required=True)
    parser.add_argument("--pydeps", type=Path, required=True)
    parser.add_argument("--reference-nsf", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()

    source = args.source_nsf.resolve()
    famistudio = args.famistudio.resolve()
    reference_path = args.reference_nsf.resolve()
    build_dir = args.build_dir.resolve()
    output_dir = (args.output_dir or build_dir / "output").resolve()
    for path in (source, famistudio, reference_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    build_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    mpu_class, _ = common.load_py65(args.pydeps)
    source_raw = source.read_bytes()
    reference = reference_path.read_bytes()
    loop = common.find_loop(source_raw, mpu_class, args.max_seconds * 60)
    skipped = max(0, loop.first_audible_call - 1)
    import_start, effective_end, effective_start, pattern_frames, loop_shift = (
        choose_rotated_loop_timeline(loop, skipped)
    )
    target_patterns = effective_end // pattern_frames
    loop_pattern = (
        None if effective_start is None else effective_start // pattern_frames
    )

    imported = build_dir / "imported.txt"
    recorded = build_dir / "recorded.txt"
    compacted = build_dir / OUTPUT_PROJECT
    raw_nsf = build_dir / "raw_compacted.nsf"
    final_nsf = output_dir / OUTPUT_NSF
    import_seconds = (effective_end + 60) // 60 + 2
    import_log = common.run_checked(
        [
            str(famistudio),
            str(source),
            "famistudio-txt-export",
            str(imported),
            f"-nsf-import-duration:{import_seconds}",
            f"-nsf-import-pattern-length:{pattern_frames}",
            f"-nsf-import-start-frame:{import_start}",
            "-famistudio-txt-cleanup",
        ]
    )
    common.rewrite_project(
        imported,
        recorded,
        project_name="Flapper Girl - ROM common driver soft-data rebuild",
        title="Flapper Girl - 琉妮精修（ROM同驱动柔和数据版）",
        target_patterns=target_patterns,
        loop_pattern=loop_pattern,
        expected_pattern_frames=pattern_frames,
    )
    compaction = compact_recorded_project(recorded, compacted)
    export_log = common.run_checked(
        [
            str(famistudio),
            str(compacted),
            "nsf-export",
            str(raw_nsf),
            "-nsf-export-mode:ntsc",
        ]
    )
    common.bind_common_driver(raw_nsf, reference, final_nsf)

    final = final_nsf.read_bytes()
    if final[common.DRIVER_SLICE] != reference[common.DRIVER_SLICE]:
        raise AssertionError("candidate does not contain the exact ROM common driver")
    raw_generated = raw_nsf.read_bytes()
    compare_frames = min(
        effective_end + (loop.loop_length or 120), args.max_seconds * 60
    )
    generated_states = common.trace_audio_semantics(
        raw_generated, mpu_class, compare_frames
    )
    rebound_states = common.trace_audio_semantics(final, mpu_class, compare_frames)
    driver_rebind_mismatches = sum(
        left != right for left, right in zip(generated_states, rebound_states)
    )
    fidelity = common.compare_source_to_conversion(
        source_raw,
        final,
        mpu_class=mpu_class,
        loop=loop,
        import_start_frame=import_start,
    )
    report = {
        "format": "Flapper Girl softened-data rebuild with ROM common driver v1",
        "source": str(source),
        "sourceSha256": digest(source_raw),
        "reference": str(reference_path),
        "referenceDriverSha256": digest(reference[common.DRIVER_SLICE]),
        "loop": loop.__dict__,
        "importStartFrame": import_start,
        "loopBoundaryShiftFrames": loop_shift,
        "patternFrames": pattern_frames,
        "compaction": compaction,
        "rawExportBytes": len(raw_generated),
        "candidate": str(final_nsf),
        "candidateBytes": len(final),
        "fitsCurrentRomSingle8KiBDataBank": len(final) <= 0x3080,
        "candidateSha256": digest(final),
        "candidateDriverSha256": digest(final[common.DRIVER_SLICE]),
        "candidateSongDataSha256": digest(final[common.DRIVER_SLICE.stop :]),
        "driverRebindMismatchFrames": driver_rebind_mismatches,
        "sourceFidelity": fidelity,
        "sourceFidelityPassed": fidelity_passed(fidelity),
        "importLog": import_log.strip(),
        "exportLog": export_log.strip(),
    }
    report_path = build_dir / "构建校验.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if driver_rebind_mismatches or not report["sourceFidelityPassed"]:
        raise RuntimeError(f"fidelity validation failed; inspect {report_path}")


if __name__ == "__main__":
    main()
