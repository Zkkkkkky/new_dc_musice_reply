from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dc_cipher.core import (  # noqa: E402
    ACTIVE_PAIR_OFFSET,
    BASE_PRG_SIZE,
    DECRYPTED_SELECTOR,
    ENCRYPTED_SELECTOR,
    EXPANDED_PRG_SIZE,
    EXPANDED_SELECTOR_OFFSET,
    EXPECTED_CHR_SIZE,
    ORIGINAL_SELECTOR_OFFSET,
    POINTER_VALUE,
    STORED_PAIR_OFFSET,
    CipherAction,
    CipherState,
    RomCipherError,
    analyze_rom,
    expected_changed_offsets,
    parse_rom_layout,
    save_transformed_copy,
    transform_rom,
)


def make_rom(prg_size: int, state: CipherState = CipherState.DECRYPTED) -> bytes:
    header = bytearray(16)
    header[:4] = b"NES\x1a"
    header[4] = prg_size // 0x4000
    header[5] = EXPECTED_CHR_SIZE // 0x2000
    header[6] = 0x23
    header[7] = 0xC0
    rom = bytearray(header + bytearray(prg_size + EXPECTED_CHR_SIZE))
    if state == CipherState.DECRYPTED:
        rom[ACTIVE_PAIR_OFFSET : ACTIVE_PAIR_OFFSET + 2] = POINTER_VALUE
        rom[ORIGINAL_SELECTOR_OFFSET] = DECRYPTED_SELECTOR
        if prg_size == EXPANDED_PRG_SIZE:
            rom[EXPANDED_SELECTOR_OFFSET] = DECRYPTED_SELECTOR
    elif state == CipherState.ENCRYPTED:
        rom[STORED_PAIR_OFFSET : STORED_PAIR_OFFSET + 2] = POINTER_VALUE
        rom[ORIGINAL_SELECTOR_OFFSET] = ENCRYPTED_SELECTOR
        if prg_size == EXPANDED_PRG_SIZE:
            rom[EXPANDED_SELECTOR_OFFSET] = ENCRYPTED_SELECTOR
    return bytes(rom)


class LayoutAndStateTests(unittest.TestCase):
    def test_recognizes_base_and_expanded_layouts(self) -> None:
        base = parse_rom_layout(make_rom(BASE_PRG_SIZE))
        expanded = parse_rom_layout(make_rom(EXPANDED_PRG_SIZE))
        self.assertFalse(base.expanded)
        self.assertTrue(expanded.expanded)
        self.assertEqual(base.expected_file_size, 0x0C0010)
        self.assertEqual(expanded.expected_file_size, 0x140010)

    def test_rejects_wrong_mapper_and_wrong_size(self) -> None:
        wrong_mapper = bytearray(make_rom(EXPANDED_PRG_SIZE))
        wrong_mapper[7] = 0xB0
        with self.assertRaises(RomCipherError):
            parse_rom_layout(wrong_mapper)

        truncated = make_rom(EXPANDED_PRG_SIZE)[:-1]
        with self.assertRaises(RomCipherError):
            parse_rom_layout(truncated)

    def test_rejects_mismatched_runtime_fixed_bank(self) -> None:
        rom = bytearray(make_rom(EXPANDED_PRG_SIZE))
        rom[EXPANDED_SELECTOR_OFFSET] = ENCRYPTED_SELECTOR
        analysis = analyze_rom(rom)
        self.assertEqual(analysis.state, CipherState.INCONSISTENT)
        with self.assertRaises(RomCipherError):
            transform_rom(rom, CipherAction.ENCRYPT)


class TransformTests(unittest.TestCase):
    def test_expanded_encrypt_updates_only_six_offsets(self) -> None:
        original = make_rom(EXPANDED_PRG_SIZE)
        encrypted, result = transform_rom(original, CipherAction.ENCRYPT)

        self.assertEqual(result.after.state, CipherState.ENCRYPTED)
        self.assertEqual(result.changed_offsets, expected_changed_offsets(result.before.layout))
        self.assertEqual(
            set(result.changed_offsets),
            {
                ACTIVE_PAIR_OFFSET,
                ACTIVE_PAIR_OFFSET + 1,
                STORED_PAIR_OFFSET,
                STORED_PAIR_OFFSET + 1,
                ORIGINAL_SELECTOR_OFFSET,
                EXPANDED_SELECTOR_OFFSET,
            },
        )
        self.assertEqual(encrypted[ORIGINAL_SELECTOR_OFFSET], ENCRYPTED_SELECTOR)
        self.assertEqual(encrypted[EXPANDED_SELECTOR_OFFSET], ENCRYPTED_SELECTOR)

    def test_base_encrypt_updates_only_five_offsets(self) -> None:
        original = make_rom(BASE_PRG_SIZE)
        _, result = transform_rom(original, CipherAction.ENCRYPT)
        self.assertEqual(len(result.changed_offsets), 5)
        self.assertNotIn(EXPANDED_SELECTOR_OFFSET, result.changed_offsets)

    def test_expanded_round_trip_is_exact(self) -> None:
        original = make_rom(EXPANDED_PRG_SIZE)
        encrypted, _ = transform_rom(original, CipherAction.ENCRYPT)
        decrypted, result = transform_rom(encrypted, CipherAction.DECRYPT)
        self.assertEqual(result.after.state, CipherState.DECRYPTED)
        self.assertEqual(decrypted, original)

    def test_refuses_repeated_or_wrong_direction(self) -> None:
        decrypted = make_rom(EXPANDED_PRG_SIZE, CipherState.DECRYPTED)
        encrypted = make_rom(EXPANDED_PRG_SIZE, CipherState.ENCRYPTED)
        with self.assertRaises(RomCipherError):
            transform_rom(decrypted, CipherAction.DECRYPT)
        with self.assertRaises(RomCipherError):
            transform_rom(encrypted, CipherAction.ENCRYPT)

    def test_save_as_preserves_source_and_verifies_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nes"
            encrypted = Path(directory) / "encrypted.nes"
            restored = Path(directory) / "restored.nes"
            original = make_rom(EXPANDED_PRG_SIZE)
            source.write_bytes(original)

            first = save_transformed_copy(source, encrypted, CipherAction.ENCRYPT)
            second = save_transformed_copy(encrypted, restored, CipherAction.DECRYPT)

            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(restored.read_bytes(), original)
            self.assertEqual(first.transform.after.state, CipherState.ENCRYPTED)
            self.assertEqual(second.transform.after.state, CipherState.DECRYPTED)
            with self.assertRaises(RomCipherError):
                save_transformed_copy(source, source, CipherAction.ENCRYPT)


if __name__ == "__main__":
    unittest.main()

