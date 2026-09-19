#!/usr/bin/env python3
"""Build a Python-free, single-file Windows DC ROM cipher executable."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
ENTRY_POINT = SOURCE_ROOT / "dc_cipher" / "app.pyw"
BUILD_ROOT = ROOT / "build" / "dc-cipher-exe"
PYINSTALLER_DIST = BUILD_ROOT / "dist"
PYINSTALLER_WORK = BUILD_ROOT / "work"
PYINSTALLER_SPEC = BUILD_ROOT / "spec"
BUILT_EXE = PYINSTALLER_DIST / "ExpandedDcCipher.exe"
DELIVERY_EXE = ROOT / "dist" / "tools" / "\u6269\u5bb9ROM\u52a0\u5bc6\u89e3\u5bc6\u5de5\u5177.exe"
REQUIRED_PYINSTALLER = "6.22.3"
REQUIRED_PYWIN32_CTYPES = "0.2.3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    try:
        installed_pyinstaller = version("pyinstaller")
    except PackageNotFoundError as error:
        raise RuntimeError(
            "\u672a\u5b89\u88c5 PyInstaller\uff1b\u8bf7\u5148\u5b89\u88c5 "
            "tools/dc_cipher_packaging_requirements.txt\u3002"
        ) from error
    if installed_pyinstaller != REQUIRED_PYINSTALLER:
        raise RuntimeError(
            f"\u9700\u8981 PyInstaller {REQUIRED_PYINSTALLER}\uff0c"
            f"\u5f53\u524d\u662f {installed_pyinstaller}\u3002"
        )
    try:
        installed_pywin32_ctypes = version("pywin32-ctypes")
    except PackageNotFoundError as error:
        raise RuntimeError(
            "未安装 pywin32-ctypes；请先安装 tools/title_editor_packaging_requirements.txt。"
        ) from error
    if installed_pywin32_ctypes != REQUIRED_PYWIN32_CTYPES:
        raise RuntimeError(
            f"需要 pywin32-ctypes {REQUIRED_PYWIN32_CTYPES}，"
            f"当前是 {installed_pywin32_ctypes}。"
        )

    resolved_build = BUILD_ROOT.resolve()
    workspace_build = (ROOT / "build").resolve()
    if not resolved_build.is_relative_to(workspace_build):
        raise RuntimeError(f"\u62d2\u7edd\u6e05\u7406 build \u4ee5\u5916\u7684\u8def\u5f84\uff1a{resolved_build}")
    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    PYINSTALLER_DIST.mkdir(parents=True)
    PYINSTALLER_WORK.mkdir(parents=True)
    PYINSTALLER_SPEC.mkdir(parents=True)

    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "1"
    environment["SOURCE_DATE_EPOCH"] = "315532800"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--noupx",
        "--name",
        "ExpandedDcCipher",
        "--paths",
        str(SOURCE_ROOT),
        "--distpath",
        str(PYINSTALLER_DIST),
        "--workpath",
        str(PYINSTALLER_WORK),
        "--specpath",
        str(PYINSTALLER_SPEC),
        str(ENTRY_POINT),
    ]
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    if not BUILT_EXE.is_file():
        raise RuntimeError(f"\u672a\u751f\u6210\u9884\u671f EXE\uff1a{BUILT_EXE}")

    DELIVERY_EXE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUILT_EXE, DELIVERY_EXE)
    print(f"exe:    {DELIVERY_EXE}")
    print(f"size:   {DELIVERY_EXE.stat().st_size}")
    print(f"sha256: {sha256(DELIVERY_EXE)}")


if __name__ == "__main__":
    main()
