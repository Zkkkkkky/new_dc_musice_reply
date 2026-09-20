"""Convert the five Mitsume ga Tooru NSF rips to the project's common driver.

The source files all contain the same unbanked $8000-$B7B4 payload and differ
only in the immediate song number at $B7B1.  FamiStudio's NSF importer records
the audible 2A03 state into an editable project.  The generated NSF song data
is then rebound to the exact 4 KiB $F000/$F100/$F160 driver page used by the
refined tracks in this repository.

Inputs are never modified.  Intermediate projects and previews belong in
``build/``; versioned projects/NSFs and delivery copies are written only when
their directories are explicitly selected (the repository defaults are safe).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFERENCE = (
    ROOT
    / "assets"
    / "music"
    / "01 精修通用驱动（F000-F100-F160）"
    / "JUST COMMUNICATION - 高达EW精修.nsf"
)
DEFAULT_BUILD = ROOT / "build" / "mitsume_refined"
DEFAULT_ASSETS = ROOT / "assets" / "music" / "02 三目童子（精修通用驱动）"
DEFAULT_DIST = ROOT / "dist" / "music" / "三目童子（精修通用驱动）"
EXPECTED_ENTRY = bytes.fromhex("00 F0 00 F1 60 F1")
EXPECTED_BANK_INIT = bytes(range(1, 8)) + b"\x00"
DRIVER_SLICE = slice(0x80, 0x1080)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_py65(pydeps: Path | None) -> tuple[type, object]:
    if pydeps is not None:
        sys.path.insert(0, str(pydeps.resolve()))
    try:
        from py65.devices.mpu6502 import MPU  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError(
            "py65 is required; pass --pydeps pointing at a directory containing py65"
        ) from exc
    return MPU, MPU


class NsfMemory:
    def __init__(self, raw: bytes):
        if raw[:5] != b"NESM\x1a":
            raise ValueError("input is not an NSF")
        self.header = raw[:0x80]
        self.payload = raw[0x80:]
        self.ram = bytearray(0x10000)
        self.banks = list(self.header[0x70:0x78])
        self.banked = any(self.banks)
        self.load_offset = (self.header[8] | (self.header[9] << 8)) & 0x0FFF
        self.current_pc = 0
        self.frame_writes: list[tuple[int, int, int]] = []
        load = self.header[8] | (self.header[9] << 8)
        if not self.banked:
            end = min(0x10000, load + len(self.payload))
            self.ram[load:end] = self.payload[: end - load]

    def _rom_index(self, address: int) -> int | None:
        if self.banked and 0x8000 <= address <= 0xFFFF:
            slot = (address - 0x8000) >> 12
            # NSF bank numbers address a conceptual 4 KiB-aligned image.  The
            # file payload itself begins at the header's load address, so a
            # source loaded at (for example) $FC00 has $C00 bytes of implicit
            # leading padding.  Subtract that padding when indexing the file.
            return (
                self.banks[slot] * 0x1000
                + (address & 0x0FFF)
                - self.load_offset
            )
        return None

    def __getitem__(self, address):
        if isinstance(address, slice):
            start, stop, step = address.indices(0x10000)
            return [self[i] for i in range(start, stop, step)]
        address &= 0xFFFF
        rom_index = self._rom_index(address)
        if rom_index is not None:
            return (
                self.payload[rom_index]
                if 0 <= rom_index < len(self.payload)
                else 0
            )
        return self.ram[address]

    def __setitem__(self, address, value):
        address &= 0xFFFF
        value &= 0xFF
        if 0x5FF8 <= address <= 0x5FFF:
            self.banks[address - 0x5FF8] = value
        elif not (self.banked and 0x8000 <= address <= 0xFFFF):
            self.ram[address] = value
        if 0x4000 <= address <= 0x4017:
            self.frame_writes.append((self.current_pc, address, value))


def call_subroutine(cpu, memory: NsfMemory, address: int, max_steps: int) -> int:
    return_pc = 0x4FFF
    cpu.sp = 0xFF
    cpu.stPushWord(return_pc)
    cpu.pc = address
    for count in range(1, max_steps + 1):
        memory.current_pc = cpu.pc
        cpu.step()
        if cpu.pc == return_pc + 1:
            return count
    raise RuntimeError(
        f"routine ${address:04X} exceeded {max_steps} instructions at ${cpu.pc:04X}"
    )


def state_digest(cpu, memory: NsfMemory) -> bytes:
    digest = hashlib.sha256()
    # NES internal RAM, APU register image, and cartridge WRAM cover the mutable
    # state used by both the original driver and the FamiStudio export.
    digest.update(memory.ram[:0x0800])
    digest.update(memory.ram[0x4000:0x4018])
    digest.update(memory.ram[0x6000:0x8000])
    digest.update(bytes((cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp, *memory.banks)))
    return digest.digest()


def audible(memory: NsfMemory) -> bool:
    status = memory.ram[0x4015]
    pulse1 = bool(status & 0x01) and bool(memory.ram[0x4000] & 0x0F)
    pulse2 = bool(status & 0x02) and bool(memory.ram[0x4004] & 0x0F)
    triangle = bool(status & 0x04) and bool(memory.ram[0x4008] & 0x7F)
    noise = bool(status & 0x08) and bool(memory.ram[0x400C] & 0x0F)
    dmc = bool(status & 0x10)
    return pulse1 or pulse2 or triangle or noise or dmc


def audible_apu_state(state: bytes) -> bool:
    status = state[0x15]
    pulse1 = bool(status & 0x01) and bool(state[0x00] & 0x0F)
    pulse2 = bool(status & 0x02) and bool(state[0x04] & 0x0F)
    triangle = bool(status & 0x04) and bool(state[0x08] & 0x7F)
    noise = bool(status & 0x08) and bool(state[0x0C] & 0x0F)
    dmc = bool(status & 0x10)
    return pulse1 or pulse2 or triangle or noise or dmc


@dataclass(frozen=True)
class LoopInfo:
    first_audible_call: int
    loop_start: int | None
    loop_end: int
    loop_length: int | None
    one_shot: bool
    frames_scanned: int
    detection: str


def find_apu_period(states: list[bytes], first_audible: int) -> LoopInfo:
    # A one-shot track normally reaches a long, muted, register-stable tail.
    tail_state = states[-1]
    tail_start = len(states) - 1
    while tail_start > 0 and states[tail_start - 1] == tail_state:
        tail_start -= 1
    if len(states) - tail_start >= 300 and not audible_apu_state(tail_state):
        return LoopInfo(
            first_audible_call=first_audible,
            loop_start=None,
            loop_end=max(tail_start, first_audible),
            loop_length=None,
            one_shot=True,
            frames_scanned=len(states),
            detection="stable-muted-APU-tail",
        )

    # Some original engines keep a monotonic bookkeeping byte even though the
    # audible register sequence loops exactly.  Locate an eventual period by
    # hashing two seconds of APU state, then require that the entire remaining
    # tail repeats for at least three cycles.  This rejects coincidental repeated
    # bars in the non-looping introduction.
    window = 120
    if len(states) < window * 3:
        raise RuntimeError("APU trace is too short for loop detection")
    occurrences: dict[bytes, list[int]] = {}
    candidates: list[tuple[int, int]] = []
    for start in range(0, len(states) - window + 1):
        block_hash = hashlib.blake2b(
            b"".join(states[start : start + window]), digest_size=16
        ).digest()
        previous_starts = occurrences.setdefault(block_hash, [])
        for previous in previous_starts:
            period = start - previous
            if period < 300 or previous + period * 3 > len(states):
                continue
            if states[previous : previous + window] != states[start : start + window]:
                continue
            if all(
                states[index] == states[index + period]
                for index in range(previous, len(states) - period)
            ):
                candidates.append((previous, period))
        # Retain the first occurrence (useful for the true loop start) plus the
        # latest few, without allowing a highly repetitive block to grow large.
        if len(previous_starts) < 8:
            previous_starts.append(start)
        else:
            previous_starts[-1] = start
    if not candidates:
        raise RuntimeError("no exact eventual APU period found")
    loop_start, loop_length = min(candidates, key=lambda item: (item[0], item[1]))
    return LoopInfo(
        first_audible_call=first_audible,
        loop_start=loop_start,
        loop_end=loop_start + loop_length,
        loop_length=loop_length,
        one_shot=False,
        frames_scanned=len(states),
        detection="exact-eventual-APU-period",
    )


def find_loop(raw: bytes, mpu_class, max_frames: int) -> LoopInfo:
    header = raw[:0x80]
    init = header[0x0A] | (header[0x0B] << 8)
    play = header[0x0C] | (header[0x0D] << 8)
    memory = NsfMemory(raw)
    cpu = mpu_class(memory=memory, pc=init)
    cpu.a = 0
    cpu.x = 0
    cpu.y = 0
    call_subroutine(cpu, memory, init, 2_000_000)

    seen: dict[bytes, int] = {state_digest(cpu, memory): 0}
    first_audible = 0
    apu_states: list[bytes] = []
    for frame in range(1, max_frames + 1):
        memory.frame_writes.clear()
        call_subroutine(cpu, memory, play, 500_000)
        if first_audible == 0 and audible(memory):
            first_audible = frame
        apu_states.append(bytes(memory.ram[0x4000:0x4018]))
        state = state_digest(cpu, memory)
        previous = seen.get(state)
        if previous is not None:
            length = frame - previous
            is_stable_silence = length <= 4 and not audible(memory)
            if is_stable_silence:
                return LoopInfo(
                    first_audible_call=first_audible,
                    loop_start=None,
                    loop_end=max(previous, first_audible),
                    loop_length=None,
                    one_shot=True,
                    frames_scanned=frame,
                    detection="exact-full-state-terminal",
                )
            if length >= 30:
                return LoopInfo(
                    first_audible_call=first_audible,
                    loop_start=previous,
                    loop_end=frame,
                    loop_length=length,
                    one_shot=False,
                    frames_scanned=frame,
                    detection="exact-full-state-loop",
                )
        else:
            seen[state] = frame
    return find_apu_period(apu_states, first_audible)


def trace_apu_states(raw: bytes, mpu_class, frames: int) -> list[bytes]:
    header = raw[:0x80]
    init = header[0x0A] | (header[0x0B] << 8)
    play = header[0x0C] | (header[0x0D] << 8)
    memory = NsfMemory(raw)
    cpu = mpu_class(memory=memory, pc=init)
    cpu.a = 0
    cpu.x = 0
    cpu.y = 0
    call_subroutine(cpu, memory, init, 2_000_000)
    states: list[bytes] = []
    for _ in range(frames):
        call_subroutine(cpu, memory, play, 500_000)
        states.append(bytes(memory.ram[0x4000:0x4018]))
    return states


def trace_audio_semantics(raw: bytes, mpu_class, frames: int) -> list[bytes]:
    """Trace audible targets while normalizing pulse phase-reset strategies.

    FamiStudio 4.5.3 may use the pulse sweep unit when the timer high byte
    changes by one, avoiding a waveform phase reset.  The repository's locked
    common driver writes the high byte directly.  Both keep the desired high
    bytes in $02A0/$02A1, so comparing those shadows plus all non-sweep APU
    registers proves pitch/volume/timing identity without rejecting this known
    implementation difference.
    """
    header = raw[:0x80]
    init = header[0x0A] | (header[0x0B] << 8)
    play = header[0x0C] | (header[0x0D] << 8)
    memory = NsfMemory(raw)
    cpu = mpu_class(memory=memory, pc=init)
    cpu.a = 0
    cpu.x = 0
    cpu.y = 0
    call_subroutine(cpu, memory, init, 2_000_000)
    states: list[bytes] = []
    for _ in range(frames):
        call_subroutine(cpu, memory, play, 500_000)
        states.append(
            bytes(
                (
                    memory.ram[0x4000],
                    memory.ram[0x4002],
                    memory.ram[0x02A0],
                    memory.ram[0x4004],
                    memory.ram[0x4006],
                    memory.ram[0x02A1],
                    *memory.ram[0x4008:0x4010],
                    memory.ram[0x4015],
                )
            )
        )
    return states


def trace_channel_targets(raw: bytes, mpu_class, frames: int) -> list[tuple[int, ...]]:
    """Return channel-level audible targets after each PLAY call."""
    header = raw[:0x80]
    init = header[0x0A] | (header[0x0B] << 8)
    play = header[0x0C] | (header[0x0D] << 8)
    memory = NsfMemory(raw)
    cpu = mpu_class(memory=memory, pc=init)
    cpu.a = 0
    cpu.x = 0
    cpu.y = 0
    call_subroutine(cpu, memory, init, 2_000_000)
    states: list[tuple[int, ...]] = []
    for _ in range(frames):
        call_subroutine(cpu, memory, play, 500_000)
        status = memory.ram[0x4015]
        p1_control = memory.ram[0x4000]
        p2_control = memory.ram[0x4004]
        tri_control = memory.ram[0x4008]
        noise_control = memory.ram[0x400C]
        states.append(
            (
                int(bool(status & 0x01) and bool(p1_control & 0x0F)),
                (p1_control >> 6) & 0x03,
                p1_control & 0x0F,
                memory.ram[0x4002] | ((memory.ram[0x4003] & 0x07) << 8),
                int(bool(status & 0x02) and bool(p2_control & 0x0F)),
                (p2_control >> 6) & 0x03,
                p2_control & 0x0F,
                memory.ram[0x4006] | ((memory.ram[0x4007] & 0x07) << 8),
                int(bool(status & 0x04) and bool(tri_control & 0x7F)),
                memory.ram[0x400A] | ((memory.ram[0x400B] & 0x07) << 8),
                int(bool(status & 0x08) and bool(noise_control & 0x0F)),
                noise_control & 0x0F,
                memory.ram[0x400E] & 0x8F,
                memory.ram[0x4001],
                memory.ram[0x4005],
            )
        )
    return states


def trace_dmc_events(
    raw: bytes, mpu_class, frames: int
) -> list[tuple[tuple[int, int, int, str], ...]]:
    """Return audible DPCM trigger semantics for every PLAY call.

    Sample addresses can legitimately change when FamiStudio repacks a song,
    so an event is identified by rate/loop/IRQ control, direct-load value,
    decoded length, and the hash of the bytes the APU will consume.
    """
    header = raw[:0x80]
    init = header[0x0A] | (header[0x0B] << 8)
    play = header[0x0C] | (header[0x0D] << 8)
    memory = NsfMemory(raw)
    cpu = mpu_class(memory=memory, pc=init)
    cpu.a = 0
    cpu.x = 0
    cpu.y = 0
    call_subroutine(cpu, memory, init, 2_000_000)
    frames_out: list[tuple[tuple[int, int, int, str], ...]] = []
    for _ in range(frames):
        memory.frame_writes.clear()
        call_subroutine(cpu, memory, play, 500_000)
        starts = [
            write
            for write in memory.frame_writes
            if write[1] == 0x4015 and (write[2] & 0x10)
        ]
        events: list[tuple[int, int, int, str]] = []
        for _write in starts:
            sample_address = 0xC000 + memory.ram[0x4012] * 64
            sample_length = memory.ram[0x4013] * 16 + 1
            sample = bytes(
                memory[sample_address + index] for index in range(sample_length)
            )
            events.append(
                (
                    memory.ram[0x4010],
                    memory.ram[0x4011],
                    sample_length,
                    sha256_bytes(sample),
                )
            )
        frames_out.append(tuple(events))
    return frames_out


def compare_source_to_conversion(
    source_raw: bytes,
    converted_raw: bytes,
    *,
    mpu_class,
    loop: LoopInfo,
    import_start_frame: int,
) -> dict[str, object]:
    first_source_index = max(0, loop.first_audible_call - 1)
    source_states = trace_channel_targets(source_raw, mpu_class, loop.loop_end)
    converted_frames = loop.loop_end - first_source_index + import_start_frame
    converted_states = trace_channel_targets(converted_raw, mpu_class, converted_frames)
    pairs = []
    for source_index in range(first_source_index, loop.loop_end):
        converted_index = source_index - first_source_index + import_start_frame
        pairs.append((source_states[source_index], converted_states[converted_index]))

    def tonal_metrics(base: int, sweep_index: int) -> dict[str, object]:
        on_mismatch = 0
        duty_mismatch = 0
        volume_error = 0
        compared_pitch = 0
        pitch_within_25 = 0
        max_pitch_cents = 0.0
        audible_frames = 0
        hardware_sweep_frames = 0
        for source_state, converted_state in pairs:
            source_on = source_state[base]
            converted_on = converted_state[base]
            on_mismatch += source_on != converted_on
            if not source_on:
                continue
            audible_frames += 1
            duty_mismatch += source_state[base + 1] != converted_state[base + 1]
            volume_error += abs(source_state[base + 2] - converted_state[base + 2])
            if converted_on:
                source_sweep = source_state[sweep_index]
                if (source_sweep & 0x80) and (source_sweep & 0x07):
                    # The original APU timer register image remains static while
                    # hardware sweep changes the actual audible period.  The
                    # FamiStudio importer records that evolving audible pitch,
                    # so raw-register cents are undefined for these frames.
                    hardware_sweep_frames += 1
                    continue
                source_period = source_state[base + 3]
                converted_period = converted_state[base + 3]
                if source_period and converted_period:
                    cents = abs(
                        1200.0
                        * math.log2((converted_period + 1) / (source_period + 1))
                    )
                    compared_pitch += 1
                    pitch_within_25 += cents <= 25.0
                    max_pitch_cents = max(max_pitch_cents, cents)
        return {
            "frames": len(pairs),
            "audibleFrames": audible_frames,
            "onOffMismatchFrames": on_mismatch,
            "dutyMismatchAudibleFrames": duty_mismatch,
            "meanAbsoluteVolumeError": round(
                volume_error / max(1, audible_frames), 6
            ),
            "pitchComparedFrames": compared_pitch,
            "sourceHardwareSweepFrames": hardware_sweep_frames,
            "pitchWithin25CentsPercent": round(
                100.0 * pitch_within_25 / max(1, compared_pitch), 6
            ),
            "maxPitchErrorCents": round(max_pitch_cents, 6),
        }

    triangle_on_mismatch = 0
    triangle_compared = 0
    triangle_within_25 = 0
    triangle_max_cents = 0.0
    noise_on_mismatch = 0
    noise_volume_error = 0
    noise_period_mismatch = 0
    noise_audible = 0
    for source_state, converted_state in pairs:
        triangle_on_mismatch += source_state[8] != converted_state[8]
        if source_state[8] and converted_state[8] and source_state[9] and converted_state[9]:
            cents = abs(
                1200.0
                * math.log2((converted_state[9] + 1) / (source_state[9] + 1))
            )
            triangle_compared += 1
            triangle_within_25 += cents <= 25.0
            triangle_max_cents = max(triangle_max_cents, cents)
        noise_on_mismatch += source_state[10] != converted_state[10]
        if source_state[10]:
            noise_audible += 1
            noise_volume_error += abs(source_state[11] - converted_state[11])
            noise_period_mismatch += source_state[12] != converted_state[12]

    source_dmc = trace_dmc_events(source_raw, mpu_class, loop.loop_end)
    converted_dmc = trace_dmc_events(converted_raw, mpu_class, converted_frames)
    dmc_pairs = []
    for source_index in range(first_source_index, loop.loop_end):
        converted_index = source_index - first_source_index + import_start_frame
        dmc_pairs.append((source_dmc[source_index], converted_dmc[converted_index]))
    dmc_mismatch = sum(left != right for left, right in dmc_pairs)
    source_dmc_events = [
        event
        for frame in source_dmc[first_source_index : loop.loop_end]
        for event in frame
    ]
    converted_dmc_events = [
        event
        for frame_index, frame in enumerate(converted_dmc)
        if import_start_frame
        <= frame_index
        < import_start_frame + len(dmc_pairs)
        for event in frame
    ]

    def unique_dmc_samples(
        events: list[tuple[int, int, int, str]],
    ) -> list[dict[str, object]]:
        return [
            {
                "rateControl": rate,
                "directLoad": direct,
                "bytes": length,
                "sha256": digest,
            }
            for rate, direct, length, digest in sorted(set(events))
        ]

    return {
        "comparedFrames": len(pairs),
        "sourceFrameRange": [first_source_index, loop.loop_end],
        "convertedFrameRange": [
            import_start_frame,
            converted_frames,
        ],
        "pulse1": tonal_metrics(0, 13),
        "pulse2": tonal_metrics(4, 14),
        "triangle": {
            "onOffMismatchFrames": triangle_on_mismatch,
            "pitchComparedFrames": triangle_compared,
            "pitchWithin25CentsPercent": round(
                100.0 * triangle_within_25 / max(1, triangle_compared), 6
            ),
            "maxPitchErrorCents": round(triangle_max_cents, 6),
        },
        "noise": {
            "audibleFrames": noise_audible,
            "onOffMismatchFrames": noise_on_mismatch,
            "meanAbsoluteVolumeError": round(
                noise_volume_error / max(1, noise_audible), 6
            ),
            "periodMismatchAudibleFrames": noise_period_mismatch,
        },
        "dmc": {
            "sourceTriggerCount": len(source_dmc_events),
            "convertedTriggerCount": len(converted_dmc_events),
            "triggerMismatchFrames": dmc_mismatch,
            "sourceSamples": unique_dmc_samples(source_dmc_events),
            "convertedSamples": unique_dmc_samples(converted_dmc_events),
        },
    }


def largest_common_pattern_frame(start: int, end: int) -> int:
    if end <= 0 or start < 0:
        raise ValueError((loop, skipped_frames))
    common = math.gcd(start, end) if start else end
    # FamiStudio allows up to 2048 frames per pattern and 256 patterns per
    # song.  Using only the command-line default ceiling of 256 needlessly
    # rejects valid loops whose exact boundary has a larger common divisor.
    for candidate in range(min(2048, common), 0, -1):
        if common % candidate == 0 and math.ceil(end / candidate) < 255:
            return candidate
    raise RuntimeError("cannot express exact loop within FamiStudio pattern limits")


def choose_timeline(
    loop: LoopInfo, skipped_frames: int
) -> tuple[int, int, int | None, int]:
    """Choose harmless leading-silence padding that yields exact loop patterns.

    FamiStudio's CLI removes leading silent calls.  ``-nsf-import-start-frame``
    can put that silence back, or omit a few silent frames.  Search the nearest
    padding to the source timing that makes both the loop start and end exact
    pattern boundaries.  Only inaudible leading padding is adjusted; the
    audible loop length is never changed.
    """
    offsets = sorted(
        range(0, 257), key=lambda value: (abs(value - skipped_frames), value)
    )
    for import_start_frame in offsets:
        adjustment = import_start_frame - skipped_frames
        end = loop.loop_end + adjustment
        start = None if loop.loop_start is None else loop.loop_start + adjustment
        if end <= 0 or (start is not None and start < 0):
            continue
        try:
            pattern_frames = largest_common_pattern_frame(start or 0, end)
        except RuntimeError:
            continue
        return import_start_frame, end, start, pattern_frames
    raise RuntimeError("cannot express exact loop after leading-silence alignment")


SONG_RE = re.compile(r'^(?P<prefix>\d+) \u4e09\u76ee\u7ae5\u5b50 - \d+ - (?P<title>.+)\.nsf$')


def song_title(path: Path) -> str:
    match = SONG_RE.match(path.name)
    if not match:
        return path.stem
    return match.group("title")


def run_checked(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout


def rewrite_project(
    source: Path,
    destination: Path,
    *,
    project_name: str = "Mitsume ga Tooru - refined common driver",
    title: str,
    target_patterns: int,
    loop_pattern: int | None,
    expected_pattern_frames: int,
) -> None:
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    output: list[str] = []
    song_seen = False
    pattern_frames = None
    for line in lines:
        if line.startswith("Project "):
            line = re.sub(r'Name="[^"]*"', f'Name="{project_name}"', line)
        if line.startswith("\tSong "):
            song_seen = True
            note_length_match = re.search(r'NoteLength="(\d+)"', line)
            pattern_length_match = re.search(r'PatternLength="(\d+)"', line)
            beat_length_match = re.search(r'BeatLength="(\d+)"', line)
            if not note_length_match or not pattern_length_match or not beat_length_match:
                raise ValueError("cannot parse imported song timing")
            imported_note_length = int(note_length_match.group(1))
            pattern_frames = imported_note_length * int(pattern_length_match.group(1))
            beat_frames = imported_note_length * int(beat_length_match.group(1))
            line = re.sub(r'Name="[^"]*"', f'Name="{title}"', line)
            # Match only the standalone song Length attribute.  A plain
            # ``Length=`` search would also corrupt PatternLength, BeatLength,
            # and NoteLength on the same line.
            line = re.sub(
                r'(?<=\s)Length="\d+"', f'Length="{target_patterns}"', line
            )
            if loop_pattern is None:
                line = re.sub(r' LoopPoint="\d+"', "", line)
            else:
                if 'LoopPoint="' in line:
                    line = re.sub(
                        r'LoopPoint="\d+"', f'LoopPoint="{loop_pattern}"', line
                    )
                else:
                    line += f' LoopPoint="{loop_pattern}"'
            # The 4.5.3 text exporter can emit large imported patterns with a
            # NoteLength that its own text parser rejects.  Notes are already
            # expressed in internal frame units, so normalize to one unit per
            # NTSC frame without changing any Time/Duration values.
            line = re.sub(
                r'PatternLength="\d+"', f'PatternLength="{pattern_frames}"', line
            )
            line = re.sub(r'BeatLength="\d+"', f'BeatLength="{beat_frames}"', line)
            line = re.sub(r'NoteLength="\d+"', 'NoteLength="1"', line)
            line = re.sub(r'Groove="[^"]*"', 'Groove="1"', line)
        instance = re.match(r'(\s*)PatternInstance Time="(\d+)"', line)
        if instance and int(instance.group(2)) >= target_patterns:
            continue
        output.append(line)
    if not song_seen or pattern_frames != expected_pattern_frames:
        raise ValueError(
            f"unexpected imported pattern geometry: {pattern_frames}, expected {expected_pattern_frames}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")


def override_dpcm_sample_data(
    project: Path, samples: dict[str, bytes]
) -> None:
    """Replace imported DPCM blobs with byte-exact source samples.

    FamiStudio 4.5.3's NSF importer can omit the final byte of a sample whose
    length is 16n+1, after which the exporter pads it with $00.  Replacing the
    text-project blob preserves that last audible DPCM byte.
    """
    text = project.read_text(encoding="utf-8")
    for name, data in samples.items():
        if len(data) % 16 != 1:
            raise ValueError(
                f'DPCM sample "{name}" has invalid 16n+1 length: {len(data)}'
            )
        pattern = re.compile(
            rf'(DPCMSample Name="{re.escape(name)}"[^\n]* Data=")[0-9a-fA-F]*(")'
        )
        text, count = pattern.subn(
            lambda match: match.group(1) + data.hex() + match.group(2),
            text,
        )
        if count != 1:
            raise ValueError(
                f'expected one DPCM sample named "{name}", found {count}'
            )
    project.write_text(text, encoding="utf-8")


def validate_source_set(paths: list[Path]) -> dict[str, object]:
    if len(paths) != 5:
        raise ValueError(f"expected five NSF files, found {len(paths)}")
    raws = [path.read_bytes() for path in paths]
    sizes = {len(raw) for raw in raws}
    if sizes != {0x3835}:
        raise ValueError(f"unexpected NSF sizes: {sorted(sizes)}")
    for path, raw in zip(paths, raws):
        if raw[:5] != b"NESM\x1a" or raw[8:14] != bytes.fromhex(
            "00 80 B0 B7 00 80"
        ):
            raise ValueError(f"unexpected Mitsume NSF header: {path}")
    variable = [
        offset
        for offset in range(len(raws[0]))
        if len({raw[offset] for raw in raws}) != 1
    ]
    if variable != [0x3831]:
        raise ValueError(f"source files differ outside the song selector: {variable}")
    selectors = [raw[0x3831] for raw in raws]
    if selectors != list(range(5, 10)):
        raise ValueError(f"unexpected song selectors: {selectors}")
    return {
        "commonBytes": len(raws[0]) - 1,
        "selectorFileOffset": "$3831",
        "selectorCpuAddress": "$B7B1",
        "selectors": [f"${value:02X}" for value in selectors],
    }


def bind_common_driver(
    raw_nsf: Path,
    reference: bytes,
    destination: Path,
    *,
    preserve_driver_offsets: tuple[int, ...] = (),
) -> None:
    raw = bytearray(raw_nsf.read_bytes())
    if raw[:5] != b"NESM\x1a" or raw[8:14] != EXPECTED_ENTRY:
        raise ValueError(f"unexpected generated NSF: {raw_nsf}")
    if raw[0x70:0x78] != EXPECTED_BANK_INIT or len(raw) not in (
        0x2080,
        0x3080,
        0x4080,
    ):
        raise ValueError(f"generated NSF has an unsupported bank layout: {raw_nsf}")
    generated_driver = bytes(raw[DRIVER_SLICE])
    raw[DRIVER_SLICE] = reference[DRIVER_SLICE]
    for offset in preserve_driver_offsets:
        if not 0 <= offset < DRIVER_SLICE.stop - DRIVER_SLICE.start:
            raise ValueError(f"driver offset outside the 4 KiB page: {offset}")
        raw[DRIVER_SLICE.start + offset] = generated_driver[offset]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)


def convert_one(
    source: Path,
    *,
    famistudio: Path,
    reference: bytes,
    build_dir: Path,
    assets_dir: Path,
    dist_dir: Path,
    mpu_class,
    max_frames: int,
    title_override: str | None = None,
    project_name: str = "Mitsume ga Tooru - refined common driver",
    output_prefix: str = "三目童子",
    source_selector_offset: int | None = 0x3831,
    preserve_driver_offsets: tuple[int, ...] = (),
    dpcm_sample_data_overrides: dict[str, bytes] | None = None,
) -> dict[str, object]:
    raw_source = source.read_bytes()
    title = title_override or song_title(source)
    print(f"[analyze] {title}", flush=True)
    slug = re.sub(r"[^A-Za-z0-9-]+", "-", title).strip("-").lower()
    if not slug:
        slug = f"song-{sha256_bytes(raw_source)[:8].lower()}"
    song_build = build_dir / slug
    song_build.mkdir(parents=True, exist_ok=True)
    loop_cache = song_build / "loop_analysis.json"
    source_hash = sha256_bytes(raw_source)
    if loop_cache.is_file():
        cached = json.loads(loop_cache.read_text(encoding="utf-8"))
        if cached.get("sourceSha256") == source_hash:
            loop = LoopInfo(**cached["loop"])
        else:
            loop = find_loop(raw_source, mpu_class, max_frames)
    else:
        loop = find_loop(raw_source, mpu_class, max_frames)
    loop_cache.write_text(
        json.dumps(
            {"sourceSha256": source_hash, "loop": loop.__dict__},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # FamiStudio's command-line NSF importer drops only the completely silent
    # calls before the first audible call.  A first audible call of 1 means no
    # frame was skipped.
    skipped = max(0, loop.first_audible_call - 1)
    print(
        f"[detected] {title}: detection={loop.detection} "
        f"firstAudible={loop.first_audible_call} start={loop.loop_start} "
        f"end={loop.loop_end} length={loop.loop_length} skipped={skipped}",
        flush=True,
    )
    import_start_frame, effective_end, effective_start, pattern_frames = choose_timeline(
        loop, skipped
    )
    if effective_end % pattern_frames:
        raise AssertionError((effective_end, pattern_frames))
    if effective_start is not None and effective_start % pattern_frames:
        raise AssertionError((effective_start, pattern_frames))
    target_patterns = effective_end // pattern_frames
    loop_pattern = (
        None if effective_start is None else effective_start // pattern_frames
    )
    print(
        f"[loop] {title}: detection={loop.detection} start={loop.loop_start} "
        f"end={loop.loop_end} importStart={import_start_frame} "
        f"patternFrames={pattern_frames}",
        flush=True,
    )

    imported = song_build / "imported.txt"
    project = song_build / f"{title}（精修通用驱动版）_FamiStudio.txt"
    raw_nsf = song_build / "raw.nsf"
    final_name = f"{output_prefix} - {title}（精修通用驱动版）.nsf"
    final_build = song_build / final_name

    import_seconds = math.ceil(effective_end / 60.098814) + 2
    import_log = run_checked(
        [
            str(famistudio),
            str(source),
            "famistudio-txt-export",
            str(imported),
            f"-nsf-import-duration:{import_seconds}",
            f"-nsf-import-pattern-length:{pattern_frames}",
            f"-nsf-import-start-frame:{import_start_frame}",
            "-famistudio-txt-cleanup",
        ]
    )
    if not imported.is_file():
        raise RuntimeError(f"FamiStudio did not create {imported}: {import_log}")
    rewrite_project(
        imported,
        project,
        project_name=project_name,
        title=title,
        target_patterns=target_patterns,
        loop_pattern=loop_pattern,
        expected_pattern_frames=pattern_frames,
    )
    if dpcm_sample_data_overrides:
        override_dpcm_sample_data(project, dpcm_sample_data_overrides)
    export_log = run_checked(
        [
            str(famistudio),
            str(project),
            "nsf-export",
            str(raw_nsf),
            "-nsf-export-mode:ntsc",
        ]
    )
    if not raw_nsf.is_file():
        raise RuntimeError(f"FamiStudio did not create {raw_nsf}: {export_log}")
    bind_common_driver(
        raw_nsf,
        reference,
        final_build,
        preserve_driver_offsets=preserve_driver_offsets,
    )

    raw_generated = raw_nsf.read_bytes()
    final = final_build.read_bytes()
    compare_frames = min(effective_end + (loop.loop_length or 120), max_frames)
    raw_states = trace_audio_semantics(raw_generated, mpu_class, compare_frames)
    final_states = trace_audio_semantics(final, mpu_class, compare_frames)
    mismatched_frames = [
        index
        for index, (left, right) in enumerate(zip(raw_states, final_states), start=1)
        if left != right
    ]
    if mismatched_frames:
        raise RuntimeError(
            f"accepted common driver changes audible pitch/volume state for {source.name}; "
            f"first mismatch frame {mismatched_frames[0]}"
        )

    source_fidelity = compare_source_to_conversion(
        raw_source,
        final,
        mpu_class=mpu_class,
        loop=loop,
        import_start_frame=import_start_frame,
    )
    for channel_name in ("pulse1", "pulse2"):
        channel = source_fidelity[channel_name]
        if (
            channel["onOffMismatchFrames"]
            or channel["dutyMismatchAudibleFrames"]
            or channel["meanAbsoluteVolumeError"]
            or channel["pitchWithin25CentsPercent"] != 100.0
        ):
            raise RuntimeError(f"source fidelity gate failed for {title} {channel_name}")
    triangle = source_fidelity["triangle"]
    noise = source_fidelity["noise"]
    dmc = source_fidelity["dmc"]
    if (
        triangle["onOffMismatchFrames"]
        or triangle["pitchWithin25CentsPercent"] != 100.0
        or noise["onOffMismatchFrames"]
        or noise["meanAbsoluteVolumeError"]
        or noise["periodMismatchAudibleFrames"]
        or dmc["triggerMismatchFrames"]
    ):
        raise RuntimeError(
            f"source fidelity gate failed for {title} triangle/noise/DPCM"
        )

    assets_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    project_assets = assets_dir / "projects"
    project_assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project, project_assets / project.name)
    shutil.copy2(final_build, assets_dir / final_name)
    shutil.copy2(final_build, dist_dir / final_name)
    print(f"[done] {title}: {final_name}", flush=True)

    return {
        "source": str(source),
        "sourceSha256": sha256_bytes(raw_source),
        "title": title,
        "sourceSelector": (
            f"${raw_source[source_selector_offset]:02X}"
            if source_selector_offset is not None
            else None
        ),
        "firstAudibleCall": loop.first_audible_call,
        "skippedSilentFrames": skipped,
        "importStartFrame": import_start_frame,
        "leadingSilenceAdjustmentFrames": import_start_frame - skipped,
        "oneShot": loop.one_shot,
        "sourceLoopStartFrame": loop.loop_start,
        "sourceLoopEndFrame": loop.loop_end,
        "sourceLoopLengthFrames": loop.loop_length,
        "loopDetection": loop.detection,
        "patternFrames": pattern_frames,
        "patternCount": target_patterns,
        "loopPattern": loop_pattern,
        "project": str(project_assets / project.name),
        "projectSha256": sha256_path(project_assets / project.name),
        "nsf": str(assets_dir / final_name),
        "nsfBytes": len(final),
        "nsfSha256": sha256_bytes(final),
        "driverSha256": sha256_bytes(final[DRIVER_SLICE]),
        "preservedDriverConfigOffsets": [
            f"${offset:03X}" for offset in preserve_driver_offsets
        ],
        "overriddenDpcmSamples": [
            {
                "name": name,
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
            for name, data in (dpcm_sample_data_overrides or {}).items()
        ],
        "apuStateComparedFrames": compare_frames,
        "apuStateMismatchFrames": 0,
        "sourceFidelity": source_fidelity,
        "importLog": import_log.strip(),
        "exportLog": export_log.strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert five Mitsume NSF rips to the refined common driver."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--famistudio", type=Path)
    parser.add_argument("--pydeps", type=Path)
    parser.add_argument("--reference-nsf", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    famistudio = args.famistudio
    if famistudio is None:
        candidate = input_dir.parent / ".tools" / "FamiStudio453" / "FamiStudio.exe"
        famistudio = candidate
    famistudio = famistudio.resolve()
    if not famistudio.is_file():
        raise FileNotFoundError(f"FamiStudio not found: {famistudio}")
    pydeps = args.pydeps
    if pydeps is None:
        candidate = input_dir.parent / ".tools" / "pydeps"
        if candidate.is_dir():
            pydeps = candidate
    mpu_class, _ = load_py65(pydeps)

    paths = sorted(input_dir.glob("*.nsf"))
    source_set = validate_source_set(paths)
    reference = args.reference_nsf.resolve().read_bytes()
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
    records = [
        convert_one(
            path,
            famistudio=famistudio,
            reference=reference,
            build_dir=build_dir,
            assets_dir=assets_dir,
            dist_dir=dist_dir,
            mpu_class=mpu_class,
            max_frames=args.max_seconds * 60,
        )
        for path in paths
    ]
    report = {
        "format": "Mitsume ga Tooru to refined F000/F100/F160 common driver v1",
        "sourceSet": source_set,
        "referenceNsf": str(args.reference_nsf),
        "referenceNsfSha256": sha256_bytes(reference),
        "commonDriverSha256": sha256_bytes(reference[DRIVER_SLICE]),
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
