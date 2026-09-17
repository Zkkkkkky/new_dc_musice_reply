"""Core ROM and NES 2bpp operations for the expanded title editor.

The supported DC-family layout keeps a 512 KiB-era CHR shadow after the
original PRG and appends the active CHR after the expanded PRG.  This module
parses the iNES header instead of assuming that active CHR still begins at a
fixed file offset.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile


INES_HEADER_SIZE = 0x10
BASE_PRG_SIZE = 0x80000
EXPANDED_PRG_SIZE = 0x100000
EXPECTED_CHR_SIZE = 0x40000
EXPECTED_MAPPER = 194

# In the original 256 KiB CHR, the title tile page starts here.
TITLE_CHR_REL_OFFSET = 0x14000
TITLE_BLOCK_SIZE = 0x0E00
TITLE_TILE_COLUMNS = 16
TITLE_TILE_COUNT = TITLE_BLOCK_SIZE // 16
TITLE_TILE_ROWS = TITLE_TILE_COUNT // TITLE_TILE_COLUMNS
TITLE_PIXEL_WIDTH = TITLE_TILE_COLUMNS * 8
TITLE_PIXEL_HEIGHT = TITLE_TILE_ROWS * 8


class RomFormatError(ValueError):
    """Raised when a ROM is not compatible with this project's layout."""


@dataclass(frozen=True)
class NesLayout:
    mapper: int
    prg_size: int
    chr_size: int
    prg_offset: int
    active_chr_offset: int
    title_active_offset: int
    title_shadow_offset: int
    expanded: bool
    expected_file_size: int


@dataclass(frozen=True)
class TitleCopies:
    active: bytes
    shadow: bytes
    mismatch_count: int


def parse_nes_layout(data: bytes | bytearray) -> NesLayout:
    """Parse and strictly validate a supported DC-family iNES ROM."""

    if len(data) < INES_HEADER_SIZE or bytes(data[:4]) != b"NES\x1a":
        raise RomFormatError("不是有效的 iNES ROM（文件头不是 NES\\x1A）。")

    flags6 = data[6]
    flags7 = data[7]
    if flags7 & 0x0C == 0x08:
        raise RomFormatError("暂不支持 NES 2.0 文件头。")
    if flags6 & 0x04:
        raise RomFormatError("该 ROM 带 512 字节 Trainer，不属于已验证的 DC 布局。")

    mapper = (flags6 >> 4) | (flags7 & 0xF0)
    prg_size = data[4] * 0x4000
    chr_size = data[5] * 0x2000
    prg_offset = INES_HEADER_SIZE
    active_chr_offset = prg_offset + prg_size
    expected_file_size = active_chr_offset + chr_size

    if mapper != EXPECTED_MAPPER:
        raise RomFormatError(f"需要 Mapper 194，当前是 Mapper {mapper}。")
    if prg_size not in (BASE_PRG_SIZE, EXPANDED_PRG_SIZE):
        raise RomFormatError(
            "PRG 必须是 512 KiB 原版或 1 MiB 扩容版，"
            f"当前是 {prg_size // 1024} KiB。"
        )
    if chr_size != EXPECTED_CHR_SIZE:
        raise RomFormatError(
            f"CHR 必须是 256 KiB，当前是 {chr_size // 1024} KiB。"
        )
    if len(data) != expected_file_size:
        raise RomFormatError(
            f"文件大小应为 0x{expected_file_size:X}，"
            f"当前是 0x{len(data):X}；为避免损坏尾部数据，已拒绝打开。"
        )
    if TITLE_CHR_REL_OFFSET + TITLE_BLOCK_SIZE > chr_size:
        raise RomFormatError("标题图块超出 CHR 范围。")

    expanded = prg_size == EXPANDED_PRG_SIZE
    title_active_offset = active_chr_offset + TITLE_CHR_REL_OFFSET
    if expanded:
        title_shadow_offset = prg_offset + BASE_PRG_SIZE + TITLE_CHR_REL_OFFSET
    else:
        title_shadow_offset = title_active_offset

    return NesLayout(
        mapper=mapper,
        prg_size=prg_size,
        chr_size=chr_size,
        prg_offset=prg_offset,
        active_chr_offset=active_chr_offset,
        title_active_offset=title_active_offset,
        title_shadow_offset=title_shadow_offset,
        expanded=expanded,
        expected_file_size=expected_file_size,
    )


def get_title_copies(data: bytes | bytearray, layout: NesLayout) -> TitleCopies:
    """Return the active and old-offset copies of the title tile page."""

    active = bytes(
        data[layout.title_active_offset : layout.title_active_offset + TITLE_BLOCK_SIZE]
    )
    shadow = bytes(
        data[layout.title_shadow_offset : layout.title_shadow_offset + TITLE_BLOCK_SIZE]
    )
    mismatch_count = sum(a != b for a, b in zip(active, shadow))
    return TitleCopies(active=active, shadow=shadow, mismatch_count=mismatch_count)


def apply_title_data(
    rom_data: bytes | bytearray,
    layout: NesLayout,
    title_data: bytes | bytearray,
    *,
    mirror_shadow: bool = True,
) -> bytes:
    """Return a modified ROM, updating active CHR and optionally its shadow."""

    if len(title_data) != TITLE_BLOCK_SIZE:
        raise ValueError(
            f"标题数据必须是 0x{TITLE_BLOCK_SIZE:X} 字节，"
            f"当前是 0x{len(title_data):X}。"
        )
    output = bytearray(rom_data)
    active_end = layout.title_active_offset + TITLE_BLOCK_SIZE
    output[layout.title_active_offset:active_end] = title_data
    if mirror_shadow:
        shadow_end = layout.title_shadow_offset + TITLE_BLOCK_SIZE
        output[layout.title_shadow_offset:shadow_end] = title_data
    return bytes(output)


def read_rom(path: str | os.PathLike[str]) -> tuple[bytes, NesLayout, TitleCopies]:
    data = Path(path).read_bytes()
    layout = parse_nes_layout(data)
    return data, layout, get_title_copies(data, layout)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def save_title_copy(
    source_path: str | os.PathLike[str],
    destination_path: str | os.PathLike[str],
    title_data: bytes | bytearray,
    *,
    mirror_shadow: bool = True,
) -> tuple[NesLayout, str]:
    """Create a new ROM atomically; the source path is never overwritten."""

    source = Path(source_path)
    destination = Path(destination_path)
    if _same_path(source, destination):
        raise ValueError("为保护源 ROM，请使用新文件名另存。")

    original = source.read_bytes()
    layout = parse_nes_layout(original)
    output = apply_title_data(
        original, layout, title_data, mirror_shadow=mirror_shadow
    )

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

    return layout, hashlib.sha256(output).hexdigest().upper()


def decode_title_pixels(title_data: bytes | bytearray) -> list[int]:
    """Decode 224 sequential NES 2bpp tiles into a 128x112 color-index grid."""

    if len(title_data) != TITLE_BLOCK_SIZE:
        raise ValueError("标题图块数据长度不正确。")
    pixels = [0] * (TITLE_PIXEL_WIDTH * TITLE_PIXEL_HEIGHT)
    for tile_index in range(TITLE_TILE_COUNT):
        tile_x = (tile_index % TITLE_TILE_COLUMNS) * 8
        tile_y = (tile_index // TITLE_TILE_COLUMNS) * 8
        tile_offset = tile_index * 16
        for row in range(8):
            low = title_data[tile_offset + row]
            high = title_data[tile_offset + 8 + row]
            destination_row = (tile_y + row) * TITLE_PIXEL_WIDTH + tile_x
            for column in range(8):
                mask = 1 << (7 - column)
                pixels[destination_row + column] = (
                    (1 if low & mask else 0) | (2 if high & mask else 0)
                )
    return pixels


def encode_title_pixels(pixels: list[int] | tuple[int, ...]) -> bytes:
    """Encode a 128x112 color-index grid into sequential NES 2bpp tiles."""

    expected = TITLE_PIXEL_WIDTH * TITLE_PIXEL_HEIGHT
    if len(pixels) != expected:
        raise ValueError(f"像素数必须是 {expected}。")
    output = bytearray(TITLE_BLOCK_SIZE)
    for tile_index in range(TITLE_TILE_COUNT):
        tile_x = (tile_index % TITLE_TILE_COLUMNS) * 8
        tile_y = (tile_index // TITLE_TILE_COLUMNS) * 8
        tile_offset = tile_index * 16
        for row in range(8):
            low = 0
            high = 0
            source_row = (tile_y + row) * TITLE_PIXEL_WIDTH + tile_x
            for column in range(8):
                value = int(pixels[source_row + column])
                if value < 0 or value > 3:
                    raise ValueError("像素色号只能是 0–3。")
                mask = 1 << (7 - column)
                if value & 1:
                    low |= mask
                if value & 2:
                    high |= mask
            output[tile_offset + row] = low
            output[tile_offset + 8 + row] = high
    return bytes(output)


def set_title_pixel(
    title_data: bytearray, x: int, y: int, value: int
) -> None:
    """Set one decoded pixel directly in NES 2bpp tile data."""

    if len(title_data) != TITLE_BLOCK_SIZE:
        raise ValueError("标题图块数据长度不正确。")
    if not (0 <= x < TITLE_PIXEL_WIDTH and 0 <= y < TITLE_PIXEL_HEIGHT):
        raise IndexError("像素坐标越界。")
    if value not in (0, 1, 2, 3):
        raise ValueError("像素色号只能是 0–3。")

    tile_column, pixel_x = divmod(x, 8)
    tile_row, pixel_y = divmod(y, 8)
    tile_index = tile_row * TITLE_TILE_COLUMNS + tile_column
    tile_offset = tile_index * 16
    mask = 1 << (7 - pixel_x)

    low_offset = tile_offset + pixel_y
    high_offset = tile_offset + 8 + pixel_y
    title_data[low_offset] &= (~mask) & 0xFF
    title_data[high_offset] &= (~mask) & 0xFF
    if value & 1:
        title_data[low_offset] |= mask
    if value & 2:
        title_data[high_offset] |= mask


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest().upper()

