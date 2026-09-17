"""Safe full-CHR shadow-to-active synchronization for expanded DC ROMs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile

try:
    from title_editor.core import BASE_PRG_SIZE, NesLayout, parse_nes_layout
except ImportError:
    # The portable package renames the shared parser to keep a flat directory.
    from nes_layout import BASE_PRG_SIZE, NesLayout, parse_nes_layout  # type: ignore[no-redef]


@dataclass(frozen=True)
class ChrSyncAnalysis:
    shadow_offset: int
    active_offset: int
    size: int
    mismatch_count: int
    first_shadow_difference: int | None
    last_shadow_difference: int | None
    first_active_difference: int | None
    last_active_difference: int | None


class ChrSyncError(ValueError):
    """Raised when a ROM cannot be safely synchronized by this tool."""


def _require_expanded(layout: NesLayout) -> None:
    if not layout.expanded:
        raise ChrSyncError(
            "该工具只能处理 1 MiB PRG 扩容 ROM；"
            "512 KiB PRG 原版的 CHR 没有影子/活动双副本问题。"
        )


def analyze_chr_copies(
    rom_data: bytes | bytearray, layout: NesLayout | None = None
) -> ChrSyncAnalysis:
    """Compare the complete retained 256 KiB CHR shadow with active CHR."""

    if layout is None:
        layout = parse_nes_layout(rom_data)
    _require_expanded(layout)

    shadow_offset = layout.prg_offset + BASE_PRG_SIZE
    active_offset = layout.active_chr_offset
    size = layout.chr_size
    mismatch_count = 0
    first_relative: int | None = None
    last_relative: int | None = None
    for relative in range(size):
        if rom_data[shadow_offset + relative] != rom_data[active_offset + relative]:
            mismatch_count += 1
            if first_relative is None:
                first_relative = relative
            last_relative = relative

    return ChrSyncAnalysis(
        shadow_offset=shadow_offset,
        active_offset=active_offset,
        size=size,
        mismatch_count=mismatch_count,
        first_shadow_difference=(
            None if first_relative is None else shadow_offset + first_relative
        ),
        last_shadow_difference=(
            None if last_relative is None else shadow_offset + last_relative
        ),
        first_active_difference=(
            None if first_relative is None else active_offset + first_relative
        ),
        last_active_difference=(
            None if last_relative is None else active_offset + last_relative
        ),
    )


def synchronize_chr_shadow_to_active(
    rom_data: bytes | bytearray, layout: NesLayout | None = None
) -> tuple[bytes, ChrSyncAnalysis]:
    """Copy the entire old CHR shadow to active CHR and return a new ROM."""

    if layout is None:
        layout = parse_nes_layout(rom_data)
    analysis = analyze_chr_copies(rom_data, layout)
    output = bytearray(rom_data)
    shadow_end = analysis.shadow_offset + analysis.size
    active_end = analysis.active_offset + analysis.size
    output[analysis.active_offset:active_end] = rom_data[
        analysis.shadow_offset:shadow_end
    ]

    # The operation must be a pure replacement of active-CHR differences.
    changed = 0
    outside = 0
    for index, (before, after) in enumerate(zip(rom_data, output)):
        if before == after:
            continue
        changed += 1
        if not (analysis.active_offset <= index < active_end):
            outside += 1
    if changed != analysis.mismatch_count or outside:
        raise AssertionError(
            f"CHR 同步边界验证失败：changed={changed}, outside={outside}"
        )
    return bytes(output), analysis


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def save_synchronized_copy(
    source_path: str | os.PathLike[str], destination_path: str | os.PathLike[str]
) -> tuple[ChrSyncAnalysis, str, str]:
    """Synchronize a ROM into a distinct file and return analysis and hashes."""

    source = Path(source_path)
    destination = Path(destination_path)
    if _same_path(source, destination):
        raise ChrSyncError("为保护源 ROM，请另存为新文件。")

    original = source.read_bytes()
    layout = parse_nes_layout(original)
    output, analysis = synchronize_chr_shadow_to_active(original, layout)
    source_hash = hashlib.sha256(original).hexdigest().upper()
    output_hash = hashlib.sha256(output).hexdigest().upper()

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary.write(output)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass

    # Re-open the final file so an interrupted or transformed write cannot pass.
    written = destination.read_bytes()
    written_layout = parse_nes_layout(written)
    final_analysis = analyze_chr_copies(written, written_layout)
    if final_analysis.mismatch_count != 0:
        raise AssertionError(
            f"保存后影子/活动 CHR 仍有 {final_analysis.mismatch_count} 字节不同。"
        )
    if hashlib.sha256(written).hexdigest().upper() != output_hash:
        raise AssertionError("保存后 ROM 哈希与内存结果不一致。")
    return analysis, source_hash, output_hash

