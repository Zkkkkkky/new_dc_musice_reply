from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "music" / "02 三目童子（精修通用驱动）"
DIST = ROOT / "dist" / "music" / "三目童子（精修通用驱动）"
REPORT = (
    ROOT
    / "evidence"
    / "2026-09-19-三目童子五曲精修驱动转换"
    / "构建校验.json"
)
REFERENCE = (
    ROOT
    / "assets"
    / "music"
    / "01 精修通用驱动（F000-F100-F160）"
    / "JUST COMMUNICATION - 高达EW精修.nsf"
)

EXPECTED = {
    "三目童子 - Stage 5-2（精修通用驱动版）.nsf": (
        12416,
        "17D852F5DA167E7F9687B112D4263E42E464C07C46B5AB526A375A7A69A6644E",
    ),
    "三目童子 - Stage 5-3（精修通用驱动版）.nsf": (
        8320,
        "669166B5D4D64D3CE36CE9E58D8B359182B83E916EC0B3F5B10E8C06173BF8FD",
    ),
    "三目童子 - Boss Fight（精修通用驱动版）.nsf": (
        16512,
        "76F55DD9FA5F4B0C36C044ABCDE9809D76CEAF45BCEAA62A9B5722AF6B9A9DD1",
    ),
    "三目童子 - Introduction（精修通用驱动版）.nsf": (
        8320,
        "5DE23FC50928A7A6B5F1DC5A223E3208DE64D3C9494EC7E6B1870584CD3F5868",
    ),
    "三目童子 - Ending (Epilogue)（精修通用驱动版）.nsf": (
        8320,
        "2AFBB1C43350FE54A30CA82AB80756ACE7C646966A939208947804BB4D4C4F81",
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class MitsumeRefinedConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = REFERENCE.read_bytes()
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_all_five_delivery_nsfs_are_locked(self) -> None:
        self.assertEqual({path.name for path in DIST.glob("*.nsf")}, set(EXPECTED))
        for filename, (expected_size, expected_hash) in EXPECTED.items():
            asset = ASSETS / filename
            delivery = DIST / filename
            self.assertEqual(asset.read_bytes(), delivery.read_bytes())
            self.assertEqual(asset.stat().st_size, expected_size)
            self.assertEqual(digest(asset.read_bytes()), expected_hash)

    def test_all_outputs_use_the_exact_rom_common_driver(self) -> None:
        expected_driver = self.reference[0x80:0x1080]
        self.assertEqual(
            digest(expected_driver),
            "20C0C421ADCE739DB24D8C9D445FB1FC6052C59668B3405967156833F402D431",
        )
        for filename in EXPECTED:
            raw = (ASSETS / filename).read_bytes()
            self.assertEqual(raw[:5], b"NESM\x1a")
            self.assertEqual(raw[8:14], bytes.fromhex("00 F0 00 F1 60 F1"))
            self.assertEqual(raw[0x70:0x78], bytes(range(1, 8)) + b"\x00")
            self.assertEqual(raw[0x80:0x1080], expected_driver)

    def test_editable_projects_are_present_and_frame_exact(self) -> None:
        projects = sorted((ASSETS / "projects").glob("*.txt"))
        self.assertEqual(len(projects), 5)
        for project in projects:
            text = project.read_text(encoding="utf-8")
            self.assertIn('TempoMode="FamiStudio"', text)
            self.assertIn('NoteLength="1"', text)
            self.assertIn('Groove="1"', text)

    def test_report_proves_source_fidelity_and_rebinding_identity(self) -> None:
        tracks = self.report["tracks"]
        self.assertEqual(len(tracks), 5)
        for track in tracks:
            self.assertEqual(track["apuStateMismatchFrames"], 0)
            fidelity = track["sourceFidelity"]
            for pulse in (fidelity["pulse1"], fidelity["pulse2"]):
                self.assertEqual(pulse["onOffMismatchFrames"], 0)
                self.assertEqual(pulse["dutyMismatchAudibleFrames"], 0)
                self.assertEqual(pulse["meanAbsoluteVolumeError"], 0.0)
                self.assertEqual(pulse["pitchWithin25CentsPercent"], 100.0)
            self.assertEqual(fidelity["triangle"]["onOffMismatchFrames"], 0)
            self.assertEqual(
                fidelity["triangle"]["pitchWithin25CentsPercent"], 100.0
            )
            self.assertEqual(fidelity["noise"]["onOffMismatchFrames"], 0)
            self.assertEqual(fidelity["noise"]["meanAbsoluteVolumeError"], 0.0)
            self.assertEqual(fidelity["noise"]["periodMismatchAudibleFrames"], 0)

        introduction = next(track for track in tracks if track["title"] == "Introduction")
        self.assertEqual(
            introduction["sourceFidelity"]["pulse1"]["sourceHardwareSweepFrames"],
            216,
        )
        self.assertEqual(
            introduction["sourceFidelity"]["pulse2"]["sourceHardwareSweepFrames"],
            216,
        )


if __name__ == "__main__":
    unittest.main()
