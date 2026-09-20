from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "music" / "03 忍者龙剑传（精修通用驱动）"
DIST = ROOT / "dist" / "music" / "忍者龙剑传（精修通用驱动）"
FILENAME = "忍者龙剑传 - 鲜烈之龙（4-2）（精修通用驱动版）.nsf"
PROJECT = ASSETS / "projects" / "鲜烈之龙（4-2）（精修通用驱动版）_FamiStudio.txt"
REPORT = (
    ROOT
    / "evidence"
    / "2026-09-20-鲜烈之龙精修驱动转换"
    / "构建校验.json"
)
REFERENCE = (
    ROOT
    / "assets"
    / "music"
    / "01 精修通用驱动（F000-F100-F160）"
    / "JUST COMMUNICATION - 高达EW精修.nsf"
)
EXPECTED_SIZE = 16512
EXPECTED_SHA256 = "B40503F449DAD9D00C56682F1F25A2A10EF73162A2F4C5E34139E5D4965404B5"
CONFIG_OFFSETS = (0x000, 0x003, 0x004)
DPCM = {
    "Sample 1": (
        257,
        "69157CCAF6EC03055E301E87A8FE124AA11295A171202DEE6515F6F106176D50",
    ),
    "Sample 2": (
        513,
        "74A169688ADD43FEDD74B5072F38A5F24778D5911957E3CDDE2D8E38FAD68961",
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class NinjaGaidenRefinedConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.asset = (ASSETS / FILENAME).read_bytes()
        cls.delivery = (DIST / FILENAME).read_bytes()
        cls.reference = REFERENCE.read_bytes()
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_delivery_is_locked_and_matches_asset(self) -> None:
        self.assertEqual(self.asset, self.delivery)
        self.assertEqual(len(self.asset), EXPECTED_SIZE)
        self.assertEqual(digest(self.asset), EXPECTED_SHA256)

    def test_refined_driver_core_and_dpcm_configuration(self) -> None:
        self.assertEqual(self.asset[:5], b"NESM\x1a")
        self.assertEqual(self.asset[8:14], bytes.fromhex("00 F0 00 F1 60 F1"))
        self.assertEqual(
            self.asset[0x70:0x78], bytes.fromhex("01 02 03 04 05 06 07 00")
        )
        actual = bytearray(self.asset[0x80:0x1080])
        expected = self.reference[0x80:0x1080]
        differences = [
            index for index, (left, right) in enumerate(zip(actual, expected))
            if left != right
        ]
        self.assertEqual(differences, list(CONFIG_OFFSETS))
        for offset in CONFIG_OFFSETS:
            actual[offset] = expected[offset]
        self.assertEqual(bytes(actual), expected)
        self.assertEqual(
            digest(expected),
            "20C0C421ADCE739DB24D8C9D445FB1FC6052C59668B3405967156833F402D431",
        )

    def test_editable_project_preserves_both_dpcm_samples(self) -> None:
        text = PROJECT.read_text(encoding="utf-8")
        self.assertIn('NoteLength="1"', text)
        self.assertIn('Groove="1"', text)
        for name, (expected_size, expected_hash) in DPCM.items():
            match = re.search(
                rf'DPCMSample Name="{re.escape(name)}"[^\n]* Data="([0-9a-f]+)"',
                text,
            )
            self.assertIsNotNone(match)
            data = bytes.fromhex(match.group(1))
            self.assertEqual(len(data), expected_size)
            self.assertEqual(digest(data), expected_hash)

    def test_report_proves_tonal_and_dpcm_fidelity(self) -> None:
        track = self.report["tracks"][0]
        self.assertEqual(track["apuStateMismatchFrames"], 0)
        self.assertEqual(track["sourceLoopLengthFrames"], 2496)
        self.assertEqual(track["preservedDriverConfigOffsets"], ["$000", "$003", "$004"])
        fidelity = track["sourceFidelity"]
        for pulse in (fidelity["pulse1"], fidelity["pulse2"]):
            self.assertEqual(pulse["onOffMismatchFrames"], 0)
            self.assertEqual(pulse["dutyMismatchAudibleFrames"], 0)
            self.assertEqual(pulse["meanAbsoluteVolumeError"], 0.0)
            self.assertEqual(pulse["pitchWithin25CentsPercent"], 100.0)
        self.assertEqual(fidelity["triangle"]["onOffMismatchFrames"], 0)
        self.assertEqual(fidelity["triangle"]["pitchWithin25CentsPercent"], 100.0)
        self.assertEqual(fidelity["noise"]["onOffMismatchFrames"], 0)
        self.assertEqual(fidelity["noise"]["periodMismatchAudibleFrames"], 0)
        self.assertEqual(fidelity["dmc"]["sourceTriggerCount"], 197)
        self.assertEqual(fidelity["dmc"]["convertedTriggerCount"], 197)
        self.assertEqual(fidelity["dmc"]["triggerMismatchFrames"], 0)
        self.assertEqual(
            fidelity["dmc"]["sourceSamples"], fidelity["dmc"]["convertedSamples"]
        )


if __name__ == "__main__":
    unittest.main()
