from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import add_last_impression_to_expanded_rom as patcher  # noqa: E402


ROM = ROOT / "dist" / "roms" / "新DC下_扩容16曲_LAST IMPRESSION_未绑定.nes"
NSF = (
    ROOT
    / "assets"
    / "music"
    / "01 精修通用驱动（F000-F100-F160）"
    / "LAST IMPRESSION - 高达W精修（ROM同引擎版）.nsf"
)
EXPECTED_ROM_SHA256 = "EDFA40E25C7029E747CA72A25EFF100B035C55CB817AE2840E541229358A4984"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class LastImpressionExpandedRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rom = ROM.read_bytes()
        cls.nsf = NSF.read_bytes()

    def test_locked_delivery(self) -> None:
        self.assertEqual(len(self.rom), patcher.ROM_SIZE)
        self.assertEqual(sha256(self.rom), EXPECTED_ROM_SHA256)
        self.assertEqual(
            self.rom[:8], bytes.fromhex("4E 45 53 1A 40 20 23 C0")
        )

    def test_new_song_payload_occupies_bank_78(self) -> None:
        self.assertEqual(
            patcher.bank(self.rom, patcher.DATA_BANK),
            self.nsf[0x1080:0x3080],
        )
        self.assertFalse(any(
            self.rom[patcher.bank_offset(0x79):patcher.bank_offset(0x7E)]
        ))

    def test_runtime_code_is_locked(self) -> None:
        bridge = patcher.bank(self.rom, patcher.BRIDGE_BANK)[
            patcher.BRIDGE_OFFSET:
            patcher.BRIDGE_OFFSET + patcher.NEW_BRIDGE_LENGTH
        ]
        self.assertEqual(sha256(bridge), patcher.NEW_BRIDGE_SHA256)
        for engine_bank in patcher.ENGINE_BANKS:
            wrapper = patcher.bank(self.rom, engine_bank)[
                patcher.WRAPPER_OFFSET:
                patcher.WRAPPER_OFFSET + patcher.NEW_WRAPPER_LENGTH
            ]
            self.assertEqual(sha256(wrapper), patcher.NEW_WRAPPER_SHA256)

    def test_fceux_latch_clear_is_present_twice(self) -> None:
        clear_latch = bytes.fromhex("A9 27 8D 00 50")
        self.assertEqual(
            patcher.bank(self.rom, patcher.STOCK_COPY_BANK).count(clear_latch),
            2,
        )


if __name__ == "__main__":
    unittest.main()
