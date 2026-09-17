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
        "6BB65EC535E31D7CC752E03F520AEB25E328D132E59CC69CC7C72C4D45528945",
    ),
    "新DC下": (
        "C623BBA0AE07AE3226A2AF09B1EAB1E42DB36EE3D8865D3DB20D3BF657C38CEC",
        "F917FBAB44032A0E427228F7AA2002A7148CADCF995134445C7CD03AE4BC79CB",
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


if __name__ == "__main__":
    unittest.main()
