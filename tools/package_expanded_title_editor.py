#!/usr/bin/env python3
"""Build the portable expanded-ROM title editor delivery directory and ZIP."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "src" / "title_editor"
DOC_PATH = ROOT / "docs" / "扩容ROM标题编辑器使用说明.md"
DELIVERY_ROOT = ROOT / "dist" / "tools"
DELIVERY_DIR = DELIVERY_ROOT / "扩容ROM标题编辑器"
ZIP_PATH = DELIVERY_ROOT / "扩容ROM标题编辑器.zip"

LAUNCHER = """@echo off
setlocal
where pythonw.exe >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe was not found. Install Python 3.10 or newer with Tkinter.
    pause
    exit /b 1
)
start "" pythonw.exe "%~dp0expanded_title_editor.pyw" %*
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    resolved_dist = (ROOT / "dist").resolve()
    resolved_delivery = DELIVERY_DIR.resolve()
    if not resolved_delivery.is_relative_to(resolved_dist):
        raise RuntimeError(f"拒绝清理 dist 以外的路径：{resolved_delivery}")
    DELIVERY_ROOT.mkdir(parents=True, exist_ok=True)
    if DELIVERY_DIR.exists():
        shutil.rmtree(DELIVERY_DIR)
    DELIVERY_DIR.mkdir()

    shutil.copyfile(SOURCE_DIR / "app.pyw", DELIVERY_DIR / "expanded_title_editor.pyw")
    shutil.copyfile(SOURCE_DIR / "core.py", DELIVERY_DIR / "core.py")
    shutil.copyfile(DOC_PATH, DELIVERY_DIR / "使用说明.md")
    (DELIVERY_DIR / "启动扩容ROM标题编辑器.cmd").write_text(
        LAUNCHER, encoding="ascii", newline="\r\n"
    )

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(DELIVERY_DIR.iterdir(), key=lambda item: item.name):
            info = zipfile.ZipInfo(
                filename=f"{DELIVERY_DIR.name}/{path.name}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    print(f"directory: {DELIVERY_DIR}")
    print(f"zip:       {ZIP_PATH}")
    print(f"size:      {ZIP_PATH.stat().st_size}")
    print(f"sha256:    {sha256(ZIP_PATH)}")


if __name__ == "__main__":
    main()
