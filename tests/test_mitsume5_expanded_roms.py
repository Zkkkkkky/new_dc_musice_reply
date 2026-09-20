from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "roms"
MUSIC = ROOT / "assets" / "music" / "02 三目童子（精修通用驱动）"
REPORT = (
    ROOT
    / "evidence"
    / "2026-09-20-三目童子五曲替换JUST"
    / "构建校验.json"
)
BANK_SIZE = 0x2000
HEADER_SIZE = 0x10
EXPECTED = {
    "新DC上_三目童子5曲_替换JUST.nes": (
        "6D2B3435045FA646111155A29C2D206DA17694772961C85122036CAA37A0FF1D",
        "upper",
    ),
    "新DC下_三目童子5曲_替换JUST.nes": (
        "EF2CA2468B478BD93B4F405CE7D83BBAE030CB2610300EE795FECB24C7DB7DE5",
        "lower",
    ),
}
TRACK_BANKS = {
    "三目童子 - Stage 5-2（精修通用驱动版）.nsf": 0x6F,
    "三目童子 - Stage 5-3（精修通用驱动版）.nsf": 0x79,
    "三目童子 - Boss Fight（精修通用驱动版）.nsf": 0x7A,
    "三目童子 - Introduction（精修通用驱动版）.nsf": 0x7C,
    "三目童子 - Ending (Epilogue)（精修通用驱动版）.nsf": 0x7D,
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def bank(raw: bytes, index: int) -> bytes:
    start = HEADER_SIZE + index * BANK_SIZE
    return raw[start : start + BANK_SIZE]


def split_track(path: Path) -> tuple[bytes, bytes | None]:
    payload = path.read_bytes()[0x80:]
    chunks = [payload[pos : pos + 0x1000] for pos in range(0, len(payload), 0x1000)]
    data = chunks[1] + (chunks[2] if len(chunks) >= 3 else bytes(0x1000))
    return data, chunks[3] if len(chunks) == 4 else None


class MitsumeFiveExpandedRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.roms = {name: (DIST / name).read_bytes() for name in EXPECTED}
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_deliveries_are_locked(self) -> None:
        for name, (expected_hash, _variant) in EXPECTED.items():
            raw = self.roms[name]
            self.assertEqual(len(raw), 0x140010)
            self.assertEqual(raw[:8], bytes.fromhex("4E 45 53 1A 40 20 23 C0"))
            self.assertEqual(digest(raw), expected_hash)

    def test_all_five_track_payloads_are_in_the_declared_banks(self) -> None:
        for filename, data_bank in TRACK_BANKS.items():
            expected_data, extra = split_track(MUSIC / filename)
            for raw in self.roms.values():
                self.assertEqual(bank(raw, data_bank), expected_data)
            if "Boss Fight" in filename:
                self.assertIsNotNone(extra)
                for raw in self.roms.values():
                    self.assertEqual(bank(raw, 0x7B)[:0x1000], extra)
                    self.assertEqual(
                        bank(raw, 0x7B)[0x1000:0x1D00],
                        bank(raw, 0x74)[0x1000:0x1D00],
                    )
            else:
                self.assertIsNone(extra)

    def test_reserved_and_existing_special_banks_are_preserved(self) -> None:
        upper = self.roms["新DC上_三目童子5曲_替换JUST.nes"]
        lower = self.roms["新DC下_三目童子5曲_替换JUST.nes"]
        self.assertFalse(any(upper[0x10 + 0x61 * BANK_SIZE : 0x10 + 0x64 * BANK_SIZE]))
        self.assertFalse(any(lower[0x10 + 0x61 * BANK_SIZE : 0x10 + 0x64 * BANK_SIZE]))
        self.assertFalse(any(bank(upper, 0x78)))
        locked_lower = (DIST / "新DC下_扩容16曲_LAST IMPRESSION_未绑定.nes").read_bytes()
        self.assertEqual(bank(lower, 0x78), bank(locked_lower, 0x78))
        locked_upper = (DIST / "新DC上_扩容15曲_未绑定.nes").read_bytes()
        self.assertEqual(bank(upper, 0x75)[:0x1000], bank(locked_upper, 0x75)[:0x1000])
        self.assertEqual(bank(lower, 0x75)[:0x1000], bank(locked_upper, 0x75)[:0x1000])

    def test_report_locks_commands_and_source_preservation(self) -> None:
        self.assertEqual(
            self.report["commands"],
            {
                "0xA0": "Stage 5-2",
                "0xA7": "Stage 5-3",
                "0xA8": "Boss Fight",
                "0xA9": "Introduction",
                "0xAA": "Ending (Epilogue)",
            },
        )
        self.assertEqual(self.report["replaced"]["oldDataBank"], "0x6F")
        self.assertFalse(self.report["roleOrMapBindingsAdded"])
        outputs = {item["variant"]: item for item in self.report["outputs"]}
        self.assertEqual(outputs["upper"]["sourceSha256"], "490DC9C24829827FB52918E1FF53431B047B3C04DE77BDFBCD1745411FE4CFFF")
        self.assertEqual(outputs["lower"]["sourceSha256"], "840E045A09A81CB8A9C58CA51FF9C0060F8E37826F25A58690EDAF598F1ED31C")
        self.assertEqual(outputs["upper"]["outputSha256"], EXPECTED["新DC上_三目童子5曲_替换JUST.nes"][0])
        self.assertEqual(outputs["lower"]["outputSha256"], EXPECTED["新DC下_三目童子5曲_替换JUST.nes"][0])


if __name__ == "__main__":
    unittest.main()
