from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from title_editor.core import (  # noqa: E402
    BASE_PRG_SIZE,
    EXPANDED_PRG_SIZE,
    EXPECTED_CHR_SIZE,
    TITLE_BLOCK_SIZE,
    TITLE_PIXEL_HEIGHT,
    TITLE_PIXEL_WIDTH,
    RomFormatError,
    apply_title_data,
    decode_title_pixels,
    encode_title_pixels,
    get_title_copies,
    parse_nes_layout,
    save_title_copy,
    set_title_pixel,
)


def make_rom(prg_size: int) -> bytes:
    header = bytearray(16)
    header[:4] = b"NES\x1a"
    header[4] = prg_size // 0x4000
    header[5] = EXPECTED_CHR_SIZE // 0x2000
    header[6] = 0x23
    header[7] = 0xC0
    return bytes(header + bytearray(prg_size + EXPECTED_CHR_SIZE))


class LayoutTests(unittest.TestCase):
    def test_expanded_offsets_come_from_header(self) -> None:
        rom = make_rom(EXPANDED_PRG_SIZE)
        layout = parse_nes_layout(rom)
        self.assertTrue(layout.expanded)
        self.assertEqual(layout.active_chr_offset, 0x100010)
        self.assertEqual(layout.title_active_offset, 0x114010)
        self.assertEqual(layout.title_shadow_offset, 0x094010)
        self.assertEqual(layout.expected_file_size, 0x140010)

    def test_base_rom_has_one_title_copy(self) -> None:
        rom = make_rom(BASE_PRG_SIZE)
        layout = parse_nes_layout(rom)
        self.assertFalse(layout.expanded)
        self.assertEqual(layout.active_chr_offset, 0x080010)
        self.assertEqual(layout.title_active_offset, 0x094010)
        self.assertEqual(layout.title_shadow_offset, layout.title_active_offset)

    def test_rejects_wrong_mapper(self) -> None:
        rom = bytearray(make_rom(EXPANDED_PRG_SIZE))
        rom[7] = 0xB0
        with self.assertRaises(RomFormatError):
            parse_nes_layout(rom)


class TitleDataTests(unittest.TestCase):
    def test_2bpp_round_trip(self) -> None:
        pixels = [
            (x + 2 * y) % 4
            for y in range(TITLE_PIXEL_HEIGHT)
            for x in range(TITLE_PIXEL_WIDTH)
        ]
        encoded = encode_title_pixels(pixels)
        self.assertEqual(len(encoded), TITLE_BLOCK_SIZE)
        self.assertEqual(decode_title_pixels(encoded), pixels)

    def test_single_pixel_write(self) -> None:
        title = bytearray(TITLE_BLOCK_SIZE)
        set_title_pixel(title, 7, 0, 3)
        pixels = decode_title_pixels(title)
        self.assertEqual(pixels[7], 3)
        self.assertEqual(sum(value != 0 for value in pixels), 1)

    def test_apply_updates_active_and_shadow_only(self) -> None:
        rom = make_rom(EXPANDED_PRG_SIZE)
        layout = parse_nes_layout(rom)
        title = bytes((index * 17) & 0xFF for index in range(TITLE_BLOCK_SIZE))
        output = apply_title_data(rom, layout, title)
        copies = get_title_copies(output, layout)
        self.assertEqual(copies.active, title)
        self.assertEqual(copies.shadow, title)
        self.assertEqual(copies.mismatch_count, 0)

        allowed = set(range(layout.title_active_offset, layout.title_active_offset + TITLE_BLOCK_SIZE))
        allowed.update(range(layout.title_shadow_offset, layout.title_shadow_offset + TITLE_BLOCK_SIZE))
        changed = {index for index, (old, new) in enumerate(zip(rom, output)) if old != new}
        self.assertTrue(changed)
        self.assertTrue(changed <= allowed)

    def test_save_as_does_not_overwrite_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nes"
            destination = Path(directory) / "edited.nes"
            original = make_rom(EXPANDED_PRG_SIZE)
            source.write_bytes(original)
            title = bytes([0xA5]) * TITLE_BLOCK_SIZE

            save_title_copy(source, destination, title)

            self.assertEqual(source.read_bytes(), original)
            output = destination.read_bytes()
            layout = parse_nes_layout(output)
            copies = get_title_copies(output, layout)
            self.assertEqual(copies.active, title)
            self.assertEqual(copies.shadow, title)

            with self.assertRaises(ValueError):
                save_title_copy(source, source, title)


if __name__ == "__main__":
    unittest.main()

