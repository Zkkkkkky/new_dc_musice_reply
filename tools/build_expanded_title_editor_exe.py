#!/usr/bin/env python3
"""Build a Python-free, single-file Windows title editor executable."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "src" / "title_editor"
ENTRY_POINT = SOURCE_DIR / "app.pyw"
BUILD_ROOT = ROOT / "build" / "title-editor-exe"
PYINSTALLER_DIST = BUILD_ROOT / "dist"
PYINSTALLER_WORK = BUILD_ROOT / "work"
PYINSTALLER_SPEC = BUILD_ROOT / "spec"
BUILT_EXE = PYINSTALLER_DIST / "ExpandedTitleEditor.exe"
DELIVERY_EXE = ROOT / "dist" / "tools" / "扩容ROM标题编辑器.exe"
REQUIRED_PYINSTALLER = "6.22.3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    try:
        installed_pyinstaller = version("pyinstaller")
    except PackageNotFoundError as error:
        raise RuntimeError(
            "未安装 PyInstaller；请先安装 tools/title_editor_packaging_requirements.txt。"
        ) from error
    if installed_pyinstaller != REQUIRED_PYINSTALLER:
        raise RuntimeError(
            f"需要 PyInstaller {REQUIRED_PYINSTALLER}，"
            f"当前是 {installed_pyinstaller}。"
        )

    resolved_build = BUILD_ROOT.resolve()
    resolved_workspace_build = (ROOT / "build").resolve()
    if not resolved_build.is_relative_to(resolved_workspace_build):
        raise RuntimeError(f"拒绝清理 build 以外的路径：{resolved_build}")
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
        "ExpandedTitleEditor",
        "--paths",
        str(SOURCE_DIR),
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
        raise RuntimeError(f"未生成预期 EXE：{BUILT_EXE}")

    DELIVERY_EXE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUILT_EXE, DELIVERY_EXE)
    print(f"exe:    {DELIVERY_EXE}")
    print(f"size:   {DELIVERY_EXE.stat().st_size}")
    print(f"sha256: {sha256(DELIVERY_EXE)}")


if __name__ == "__main__":
    main()
