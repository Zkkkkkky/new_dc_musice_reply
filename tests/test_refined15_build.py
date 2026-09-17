from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_refined15_roms as builder  # noqa: E402

HEADER_SIZE = 0x10
SOURCE_SIZE = 0x0C0010
OUTPUT_SIZE = 0x140010
BANK_SIZE = 0x2000

CASES = {
    "新DC上": (
        "34A669879A1310045FBF15A916B86FBCDA765B3A1B39E799D5A76A16D03BB6EF",
        "B744688EF81853833FC0ADB44828C211F61E58F5ABF1DFFACE977B1AB5D647A5",
    ),
    "新DC下": (
        "C623BBA0AE07AE3226A2AF09B1EAB1E42DB36EE3D8865D3DB20D3BF657C38CEC",
        "6663C25FA692766F8EDADCC600152C98CDBCF57943B468A9172A36656F3CEA8E",
    ),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def bank(rom: bytes, index: int) -> bytes:
    start = HEADER_SIZE + index * BANK_SIZE
    return rom[start:start + BANK_SIZE]


class Refined15BuildTests(unittest.TestCase):
    def test_locked_source_and_output_hashes(self) -> None:
        for label, (source_hash, output_hash) in CASES.items():
            source = (ROOT / "dist" / "roms" / f"{label}.nes").read_bytes()
            output = (
                ROOT / "dist" / "roms" / f"{label}_扩容15曲_未绑定.nes"
            ).read_bytes()
            self.assertEqual((len(source), sha256(source)), (SOURCE_SIZE, source_hash))
            self.assertEqual((len(output), sha256(output)), (OUTPUT_SIZE, output_hash))

    def test_old_file_body_is_a_byte_exact_prefix(self) -> None:
        for label in CASES:
            source = (ROOT / "dist" / "roms" / f"{label}.nes").read_bytes()
            output = (
                ROOT / "dist" / "roms" / f"{label}_扩容15曲_未绑定.nes"
            ).read_bytes()
            changed_header = [
                i for i, (before, after) in enumerate(zip(source[:16], output[:16]))
                if before != after
            ]
            self.assertEqual(changed_header, [4])
            self.assertEqual(output[4], 0x40)
            self.assertEqual(output[16:len(source)], source[16:])

    def test_expansion_layout_and_fceux_handoff(self) -> None:
        clear_latch = bytes.fromhex("A9 27 8D 00 50")
        for label in CASES:
            output = (
                ROOT / "dist" / "roms" / f"{label}_扩容15曲_未绑定.nes"
            ).read_bytes()
            self.assertFalse(any(bank(output, 0x61) + bank(output, 0x62) + bank(output, 0x63)))
            self.assertFalse(any(output[HEADER_SIZE + 0x78 * BANK_SIZE:HEADER_SIZE + 0x7E * BANK_SIZE]))
            self.assertEqual(bank(output, 0x60).count(clear_latch), 2)
            self.assertTrue(any(bank(output, 0x64)))
            self.assertTrue(all(any(bank(output, i)) for i in range(0x65, 0x78)))

    def test_all_fifteen_tracks_and_commands_are_locked(self) -> None:
        records, shared_driver, anime_chunk = builder.read_tracks()
        manifest = json.loads(
            (ROOT / "assets" / "music" / "refined15_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(len(records), 15)
        self.assertEqual(manifest["count"], 15)
        self.assertEqual(len(shared_driver), 0x1000)
        self.assertIsNotNone(anime_chunk)
        self.assertEqual(
            [track["command"] for track in records],
            [0x94, 0x95, 0xA5, 0x96, 0x97, 0x98, 0x99, 0x9A,
             0x9B, 0x9C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4],
        )
        self.assertEqual(
            [track["nsfSha256"] for track in records],
            [track["nsfSha256"] for track in manifest["tracks"]],
        )

    def test_relocated_driver_avoids_game_pointer_and_mapper_registers(self) -> None:
        _, shared_driver, _ = builder.read_tracks()
        relocated, mapping = builder.relocate_driver(shared_driver)
        self.assertEqual(
            [mapping[address] for address in range(0x0294, 0x0298)],
            [0x0468, 0x0469, 0x002A, 0x002B],
        )
        self.assertNotIn(0x0028, mapping.values())
        self.assertNotIn(0x0029, mapping.values())
        self.assertEqual(relocated.count(bytes.fromhex("9D F8 5F")), 0)
        self.assertEqual(relocated.count(bytes.fromhex("9D F8 48")), 2)

    def test_sfx_snapshot_conversion_keeps_complete_state(self) -> None:
        source = bytearray(BANK_SIZE)
        source[:4] = bytes.fromhex("04 80 04 80")
        table_end = 4 + builder.SFX_COUNT * 2
        for index in range(builder.SFX_COUNT):
            source[4 + index * 2:6 + index * 2] = (
                0x8000 + table_end
            ).to_bytes(2, "little")
        source[table_end:table_end + 10] = bytes.fromhex(
            "80 11 81 22 02 80 33 03 00 00"
        )

        converted = builder.convert_sfx_to_snapshots(bytes(source))
        pointer = int.from_bytes(converted[4:6], "little") - 0x8000
        self.assertEqual(
            converted[pointer:pointer + 13],
            bytes.fromhex("02 02 00 11 01 22 03 02 00 33 01 22 00"),
        )

    def test_bounded_sfx_bank_is_locked(self) -> None:
        for label in CASES:
            output = (
                ROOT / "dist" / "roms" / f"{label}_扩容15曲_未绑定.nes"
            ).read_bytes()
            self.assertEqual(
                sha256(bank(output, builder.SFX_DATA_BANK)),
                "5A9F41C54DB6A3FD8FE48358D110F141526D25406ABFA783DFE7816637BD0E41",
            )


if __name__ == "__main__":
    unittest.main()
