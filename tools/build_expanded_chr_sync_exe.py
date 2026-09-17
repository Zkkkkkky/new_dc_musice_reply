#!/usr/bin/env python3
"""Build a Python-free .NET Framework WinForms full-CHR sync executable."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "chr_sync" / "ExpandedChrSync.cs"
BUILD_ROOT = ROOT / "build" / "chr-sync-native"
BUILT_EXE = BUILD_ROOT / "ExpandedChrSync.exe"
DELIVERY_EXE = ROOT / "dist" / "tools" / "扩容ROM全CHR同步工具.exe"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def find_compiler() -> Path:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = (
        windows / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windows / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("未找到 .NET Framework 4.x C# 编译器。")


def main() -> None:
    resolved_build = BUILD_ROOT.resolve()
    workspace_build = (ROOT / "build").resolve()
    if not resolved_build.is_relative_to(workspace_build):
        raise RuntimeError(f"拒绝清理 build 以外的路径：{resolved_build}")
    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    BUILD_ROOT.mkdir(parents=True)

    compiler = find_compiler()
    command = [
        str(compiler),
        "/nologo",
        "/target:winexe",
        "/platform:anycpu",
        "/optimize+",
        "/debug-",
        "/codepage:65001",
        "/reference:System.dll",
        "/reference:System.Core.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Windows.Forms.dll",
        "/out:" + str(BUILT_EXE),
        str(SOURCE),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    if not BUILT_EXE.is_file():
        raise RuntimeError(f"未生成预期 EXE：{BUILT_EXE}")

    DELIVERY_EXE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUILT_EXE, DELIVERY_EXE)
    print(f"compiler: {compiler}")
    print(f"exe:      {DELIVERY_EXE}")
    print(f"size:     {DELIVERY_EXE.stat().st_size}")
    print(f"sha256:   {sha256(DELIVERY_EXE)}")


if __name__ == "__main__":
    main()

