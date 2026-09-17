from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chr_sync.core import (  # noqa: E402
    ChrSyncError,
    analyze_chr_copies,
    save_synchronized_copy,
    synchronize_chr_shadow_to_active,
)
from title_editor.core import (  # noqa: E402
    BASE_PRG_SIZE,
    EXPANDED_PRG_SIZE,
    EXPECTED_CHR_SIZE,
    parse_nes_layout,
)


def make_rom(prg_size: int) -> bytes:
    header = bytearray(16)
    header[:4] = b"NES\x1a"
    header[4] = prg_size // 0x4000
    header[5] = EXPECTED_CHR_SIZE // 0x2000
    header[6] = 0x23
    header[7] = 0xC0
    return bytes(header + bytearray(prg_size + EXPECTED_CHR_SIZE))


class ExpandedChrSyncTests(unittest.TestCase):
    def test_syncs_entire_shadow_to_active_and_nothing_else(self) -> None:
        rom = bytearray(make_rom(EXPANDED_PRG_SIZE))
        layout = parse_nes_layout(rom)
        shadow = layout.prg_offset + BASE_PRG_SIZE
        active = layout.active_chr_offset
        edits = {
            0x00000: 0x11,
            0x00001: 0x22,
            0x14021: 0x33,
            EXPECTED_CHR_SIZE - 1: 0x44,
        }
        for relative, value in edits.items():
            rom[shadow + relative] = value

        output, analysis = synchronize_chr_shadow_to_active(rom, layout)

        self.assertEqual(analysis.mismatch_count, len(edits))
        self.assertEqual(
            output[active : active + EXPECTED_CHR_SIZE],
            output[shadow : shadow + EXPECTED_CHR_SIZE],
        )
        changed = {
            index for index, (before, after) in enumerate(zip(rom, output)) if before != after
        }
        self.assertEqual(changed, {active + relative for relative in edits})

    def test_rejects_unexpanded_rom(self) -> None:
        rom = make_rom(BASE_PRG_SIZE)
        with self.assertRaises(ChrSyncError):
            analyze_chr_copies(rom)

    def test_save_as_preserves_source_and_verifies_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "modified-expanded.nes"
            destination = Path(directory) / "synced.nes"
            rom = bytearray(make_rom(EXPANDED_PRG_SIZE))
            layout = parse_nes_layout(rom)
            shadow = layout.prg_offset + BASE_PRG_SIZE
            rom[shadow + 0x1234] = 0xA5
            source.write_bytes(rom)

            analysis, source_hash, output_hash = save_synchronized_copy(
                source, destination
            )

            self.assertEqual(analysis.mismatch_count, 1)
            self.assertEqual(source.read_bytes(), bytes(rom))
            self.assertNotEqual(source_hash, output_hash)
            output = destination.read_bytes()
            self.assertEqual(analyze_chr_copies(output).mismatch_count, 0)

            with self.assertRaises(ChrSyncError):
                save_synchronized_copy(source, source)


if __name__ == "__main__":
    unittest.main()

