from __future__ import annotations

import hashlib
import gzip
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "modifier_launcher" / "Program.cs"
RECONCILER_SOURCE = ROOT / "src" / "modifier_launcher" / "ChrReconciler.cs"
DELIVERY = ROOT / "dist" / "tools" / "新DC扩容专用修改器"
LAUNCHER = DELIVERY / "新DC扩容专用修改器.exe"
ENGINE = DELIVERY / "内部文件" / "修改器核心.exe"
ENGINE_BACKUP = DELIVERY / "内部文件" / "修改器核心.已验证.gz"
ROOT_CONFIG = DELIVERY / "默认配置文件"
ENGINE_CONFIG = DELIVERY / "内部文件" / "默认配置文件"
ARCHIVE = ROOT / "dist" / "tools" / "新DC扩容专用修改器.zip"
EXPECTED_ENGINE_SHA256 = (
    "4C7F2980CC780253050174C7A6E00A506C7D1EA29E74B90128BDA9ABD9335947"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class ModifierSkipLauncherTests(unittest.TestCase):
    def test_source_hides_only_the_exact_legacy_launcher(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('LauncherTitle = "SRW2修改器V1.5"', source)
        self.assertIn('MainTitlePrefix = "SRW2扩容版修改器V1.0"', source)
        self.assertIn("LauncherButtonId = 110", source)
        self.assertIn("TotalSeconds >= 3.0", source)
        self.assertIn("ConcealLauncher", source)
        self.assertIn("-32000", source)

    def test_delivery_locks_the_audited_engine(self) -> None:
        self.assertEqual(ENGINE.stat().st_size, 5_701_632)
        self.assertEqual(sha256(ENGINE), EXPECTED_ENGINE_SHA256)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(EXPECTED_ENGINE_SHA256, source)

    def test_delivery_launcher_is_a_separate_pe(self) -> None:
        self.assertEqual(LAUNCHER.read_bytes()[:2], b"MZ")
        self.assertLess(LAUNCHER.stat().st_size, 100_000)
        self.assertNotEqual(sha256(LAUNCHER), sha256(ENGINE))

    def test_recovery_archive_contains_the_audited_engine(self) -> None:
        with gzip.open(ENGINE_BACKUP, "rb") as stream:
            recovered = stream.read()
        self.assertEqual(len(recovered), 5_701_632)
        self.assertEqual(hashlib.sha256(recovered).hexdigest().upper(), EXPECTED_ENGINE_SHA256)

    def test_launcher_recovers_without_running_a_changed_core(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            internal = temp / "内部文件"
            internal.mkdir()
            changed_core = internal / "修改器核心.exe"
            changed_core.write_bytes(b"changed core must not run")
            (internal / ENGINE_BACKUP.name).write_bytes(ENGINE_BACKUP.read_bytes())

            completed = subprocess.run(
                [str(LAUNCHER), "--prepare-engine", str(temp)],
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(changed_core.read_bytes(), b"changed core must not run")
            recovered = internal / "修改器核心_自动恢复.exe"
            self.assertEqual(sha256(recovered), EXPECTED_ENGINE_SHA256)

            recovered.write_bytes(b"recovered core changed after use")
            repeated = subprocess.run(
                [str(LAUNCHER), "--prepare-engine", str(temp)],
                check=False,
                timeout=30,
            )
            self.assertEqual(repeated.returncode, 0)
            self.assertEqual(sha256(recovered), EXPECTED_ENGINE_SHA256)

    def test_engine_has_an_identical_local_config_mirror(self) -> None:
        root_files = {
            path.name: path.read_bytes()
            for path in ROOT_CONFIG.iterdir()
            if path.is_file() and path.suffix.lower() in {".ini", ".dat"}
        }
        engine_files = {
            path.name: path.read_bytes()
            for path in ENGINE_CONFIG.iterdir()
            if path.is_file() and path.suffix.lower() in {".ini", ".dat"}
        }
        self.assertGreater(len(root_files), 0)
        self.assertEqual(engine_files, root_files)

    def test_reconciler_handles_each_one_sided_chr_write(self) -> None:
        size = 0x140010
        shadow = 0x080010
        active = 0x100010
        baseline = bytearray(size)
        baseline[:16] = bytes.fromhex(
            "4E 45 53 1A 40 20 23 C0 00 00 00 00 00 00 00 00"
        )
        current = bytearray(baseline)
        current[shadow + 0x123] = 0xA5
        current[active + 0x456] = 0x5A
        current[shadow + 0x789] = 0x33
        current[active + 0x789] = 0x33

        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            before_path = temp / "before.nes"
            current_path = temp / "current.nes"
            output_path = temp / "output.nes"
            before_path.write_bytes(baseline)
            current_path.write_bytes(current)
            completed = subprocess.run(
                [
                    str(LAUNCHER),
                    "--reconcile-copy",
                    str(before_path),
                    str(current_path),
                    str(output_path),
                ],
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0)
            output = output_path.read_bytes()

        self.assertEqual(output[shadow + 0x123], 0xA5)
        self.assertEqual(output[active + 0x123], 0xA5)
        self.assertEqual(output[shadow + 0x456], 0x5A)
        self.assertEqual(output[active + 0x456], 0x5A)
        self.assertEqual(output[shadow + 0x789], 0x33)
        self.assertEqual(output[active + 0x789], 0x33)
        changed = [
            index for index, (left, right) in enumerate(zip(current, output))
            if left != right
        ]
        self.assertEqual(changed, [shadow + 0x456, active + 0x123])

    def test_source_keeps_conflicts_and_layout_checks_explicit(self) -> None:
        source = RECONCILER_SOURCE.read_text(encoding="utf-8")
        launcher = SOURCE.read_text(encoding="utf-8")
        self.assertIn("shadowChanged && !activeChanged", source)
        self.assertIn("!shadowChanged && activeChanged", source)
        self.assertIn("newShadow != newActive", source)
        self.assertIn("mapper != 194", source)
        self.assertIn("MonitorRomSaves", launcher)
        self.assertIn("扩容 CHR 已自动同步", launcher)

    def test_reconciler_refuses_different_two_sided_changes(self) -> None:
        size = 0x140010
        shadow = 0x080010
        active = 0x100010
        baseline = bytearray(size)
        baseline[:16] = bytes.fromhex(
            "4E 45 53 1A 40 20 23 C0 00 00 00 00 00 00 00 00"
        )
        current = bytearray(baseline)
        current[shadow + 0x222] = 0x11
        current[active + 0x222] = 0x22

        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            before_path = temp / "before.nes"
            current_path = temp / "current.nes"
            output_path = temp / "output.nes"
            before_path.write_bytes(baseline)
            current_path.write_bytes(current)
            completed = subprocess.run(
                [
                    str(LAUNCHER),
                    "--reconcile-copy",
                    str(before_path),
                    str(current_path),
                    str(output_path),
                ],
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(output_path.exists())

    def test_portable_zip_contains_no_test_rom_or_debug_files(self) -> None:
        with zipfile.ZipFile(ARCHIVE) as archive:
            names = set(archive.namelist())
        root = "新DC扩容专用修改器/"
        self.assertIn(root + "新DC扩容专用修改器.exe", names)
        self.assertIn(root + "内部文件/修改器核心.exe", names)
        self.assertIn(root + "内部文件/修改器核心.已验证.gz", names)
        self.assertIn(root + "内部文件/默认配置文件/码表.ini", names)
        self.assertIn(root + "使用说明.md", names)
        forbidden = {".nes", ".cdl", ".deb", ".pdb"}
        self.assertFalse(any(Path(name).suffix.lower() in forbidden for name in names))


if __name__ == "__main__":
    unittest.main()
