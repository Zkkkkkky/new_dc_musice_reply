#!/usr/bin/env python3
"""Build and package the one-click launcher for the expanded legacy modifier."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "modifier_launcher" / "Program.cs"
RECONCILER_SOURCE = ROOT / "src" / "modifier_launcher" / "ChrReconciler.cs"
README_SOURCE = ROOT / "src" / "modifier_launcher" / "使用说明.md"
ENGINE_SOURCE = ROOT / "build" / "legacy_modifier" / "SRW2_expanded_chr_candidate.exe"
BUILD_ROOT = ROOT / "build" / "modifier-skip-launcher"
BUILT_LAUNCHER = BUILD_ROOT / "新DC扩容专用修改器.exe"
DELIVERY_ROOT = ROOT / "dist" / "tools" / "新DC扩容专用修改器"
DELIVERY_LAUNCHER = DELIVERY_ROOT / "新DC扩容专用修改器.exe"
DELIVERY_ENGINE = DELIVERY_ROOT / "内部文件" / "修改器核心.exe"
DELIVERY_README = DELIVERY_ROOT / "使用说明.md"
DELIVERY_ZIP = ROOT / "dist" / "tools" / "新DC扩容专用修改器.zip"
CONFIG_SOURCE = ROOT / "inputs" / "legacy_modifier" / "默认配置文件"

EXPECTED_ENGINE_SIZE = 5_701_632
EXPECTED_ENGINE_SHA256 = (
    "4C7F2980CC780253050174C7A6E00A506C7D1EA29E74B90128BDA9ABD9335947"
)
ALLOWED_CONFIG_SUFFIXES = {".ini", ".dat"}


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


def validate_engine() -> None:
    if not ENGINE_SOURCE.is_file():
        raise RuntimeError(
            "缺少扩容 CHR 补丁引擎，请先运行 tools/patch_legacy_modifier_expanded_chr.py。"
        )
    actual_size = ENGINE_SOURCE.stat().st_size
    actual_hash = sha256(ENGINE_SOURCE)
    if actual_size != EXPECTED_ENGINE_SIZE or actual_hash != EXPECTED_ENGINE_SHA256:
        raise RuntimeError(
            "修改器引擎不是已审计版本："
            f"size={actual_size}, sha256={actual_hash}"
        )


def rebuild_zip() -> None:
    temp_zip = BUILD_ROOT / "新DC扩容专用修改器.zip"
    with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(DELIVERY_ROOT.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() in {".nes", ".cdl", ".deb"}:
                raise RuntimeError(f"交付目录包含禁止打包的文件：{path}")
            relative = Path(DELIVERY_ROOT.name) / path.relative_to(DELIVERY_ROOT)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 9, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    shutil.copyfile(temp_zip, DELIVERY_ZIP)


def main() -> None:
    validate_engine()
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
        "/reference:System.Windows.Forms.dll",
        "/out:" + str(BUILT_LAUNCHER),
        str(SOURCE),
        str(RECONCILER_SOURCE),
    ]
    subprocess.run(command, cwd=ROOT, check=True)

    DELIVERY_LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
    DELIVERY_ENGINE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUILT_LAUNCHER, DELIVERY_LAUNCHER)
    shutil.copyfile(ENGINE_SOURCE, DELIVERY_ENGINE)
    shutil.copyfile(README_SOURCE, DELIVERY_README)

    # The legacy core resolves its data tables relative to the executable,
    # not only from the process working directory.  Keep the user-facing
    # copy at the package root and mirror the same files next to the core;
    # otherwise opening some ROMs leaves its lookup arrays empty and raises
    # an out-of-range runtime error.
    config_destinations = (
        DELIVERY_ROOT / "默认配置文件",
        DELIVERY_ENGINE.parent / "默认配置文件",
    )
    for config_destination in config_destinations:
        config_destination.mkdir(parents=True, exist_ok=True)
        for source in sorted(CONFIG_SOURCE.iterdir()):
            if source.is_file() and source.suffix.lower() in ALLOWED_CONFIG_SUFFIXES:
                shutil.copyfile(source, config_destination / source.name)

    rebuild_zip()
    print(f"compiler: {compiler}")
    print(
        f"launcher: {DELIVERY_LAUNCHER} | {DELIVERY_LAUNCHER.stat().st_size} | "
        f"{sha256(DELIVERY_LAUNCHER)}"
    )
    print(
        f"engine:   {DELIVERY_ENGINE} | {DELIVERY_ENGINE.stat().st_size} | "
        f"{sha256(DELIVERY_ENGINE)}"
    )
    print(
        f"zip:      {DELIVERY_ZIP} | {DELIVERY_ZIP.stat().st_size} | "
        f"{sha256(DELIVERY_ZIP)}"
    )


if __name__ == "__main__":
    main()
