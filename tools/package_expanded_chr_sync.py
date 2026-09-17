#!/usr/bin/env python3
"""Build the portable full-CHR shadow synchronization delivery."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SYNC_SOURCE = ROOT / "src" / "chr_sync"
LAYOUT_SOURCE = ROOT / "src" / "title_editor" / "core.py"
DOC_SOURCE = ROOT / "docs" / "扩容ROM全CHR同步工具使用说明.md"
DIST_ROOT = ROOT / "dist" / "tools"
DIST_DIR = DIST_ROOT / "扩容ROM全CHR同步工具"
ZIP_PATH = DIST_ROOT / "扩容ROM全CHR同步工具.zip"

LAUNCHER = """@echo off
setlocal
where pythonw.exe >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe was not found. Install Python 3.10 or newer with Tkinter.
    pause
    exit /b 1
)
start "" pythonw.exe "%~dp0expanded_chr_sync.pyw" %*
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    resolved_dist = (ROOT / "dist").resolve()
    resolved_delivery = DIST_DIR.resolve()
    if not resolved_delivery.is_relative_to(resolved_dist):
        raise RuntimeError(f"拒绝清理 dist 以外的路径：{resolved_delivery}")

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir()

    shutil.copyfile(SYNC_SOURCE / "app.pyw", DIST_DIR / "expanded_chr_sync.pyw")
    shutil.copyfile(SYNC_SOURCE / "core.py", DIST_DIR / "chr_sync_core.py")
    shutil.copyfile(LAYOUT_SOURCE, DIST_DIR / "nes_layout.py")
    shutil.copyfile(DOC_SOURCE, DIST_DIR / "使用说明.md")
    (DIST_DIR / "启动扩容ROM全CHR同步工具.cmd").write_text(
        LAUNCHER, encoding="ascii", newline="\r\n"
    )

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(DIST_DIR.iterdir(), key=lambda item: item.name):
            info = zipfile.ZipInfo(
                filename=f"{DIST_DIR.name}/{path.name}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )

    print(f"directory: {DIST_DIR}")
    print(f"zip:       {ZIP_PATH}")
    print(f"size:      {ZIP_PATH.stat().st_size}")
    print(f"sha256:    {sha256(ZIP_PATH)}")


if __name__ == "__main__":
    main()

