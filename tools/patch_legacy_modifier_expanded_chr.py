#!/usr/bin/env python3
"""Patch the audited legacy SRW2 modifier to use expanded-ROM active CHR.

The original executable hard-codes the 512 KiB-PRG CHR base (0x080010) in
thirteen code immediates and one serialized initialization value.  The
expanded DC layout moves active CHR to 0x100010.  This tool changes only those
fourteen constants, refuses unknown input hashes, never overwrites its input,
and emits a machine-readable audit record next to the candidate executable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "inputs" / "legacy_modifier" / "SRW2_patched.exe"
DEFAULT_OUTPUT = ROOT / "build" / "legacy_modifier" / "SRW2_expanded_chr_candidate.exe"

EXPECTED_INPUT_SIZE = 5_701_632
EXPECTED_INPUT_SHA256 = "FF1C1C5799FDB8F34DF355D761B382C6946CDADC6810772862947E892E8B4C27"
OLD_CHR_BASE = 0x080010
NEW_CHR_BASE = 0x100010

# Raw-file positions of the imm32/data values in the rebuilt PE.  The first
# thirteen are executable-code operands; the final one is serialized data.
PATCH_OFFSETS = (
    0x0BB2C9,
    0x0BC74F,
    0x176EE2,
    0x177200,
    0x19F164,
    0x1B61C7,
    0x1BBA90,
    0x1BD981,
    0x1C34AA,
    0x1C8F62,
    0x1C9280,
    0x1CFB13,
    0x1F3844,
    0x5108AC,
)


class ModifierPatchError(ValueError):
    """Raised when the executable does not match the audited binary."""


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def find_all(data: bytes | bytearray, needle: bytes) -> tuple[int, ...]:
    positions: list[int] = []
    start = 0
    while True:
        position = data.find(needle, start)
        if position < 0:
            return tuple(positions)
        positions.append(position)
        start = position + 1


def patch_modifier_bytes(
    data: bytes,
    *,
    offsets: tuple[int, ...] = PATCH_OFFSETS,
    require_exclusive_matches: bool = True,
) -> tuple[bytes, list[dict[str, object]]]:
    """Patch known CHR-base constants and return output plus audit entries."""

    old = struct.pack("<I", OLD_CHR_BASE)
    new = struct.pack("<I", NEW_CHR_BASE)
    if require_exclusive_matches:
        actual = find_all(data, old)
        if actual != offsets:
            raise ModifierPatchError(
                "0x80010 常量位置与已审计版本不符："
                f"\n期望 {[hex(value) for value in offsets]}"
                f"\n实际 {[hex(value) for value in actual]}"
            )

    output = bytearray(data)
    audit: list[dict[str, object]] = []
    for index, offset in enumerate(offsets):
        if bytes(output[offset : offset + 4]) != old:
            raise ModifierPatchError(
                f"偏移 0x{offset:X} 的原字节不是 {old.hex().upper()}。"
            )
        output[offset : offset + 4] = new
        audit.append(
            {
                "index": index,
                "kind": "code-imm32" if index < 13 else "serialized-data",
                "fileOffset": f"0x{offset:X}",
                "oldBytes": old.hex().upper(),
                "newBytes": new.hex().upper(),
                "oldValue": f"0x{OLD_CHR_BASE:X}",
                "newValue": f"0x{NEW_CHR_BASE:X}",
            }
        )

    changed = [
        index for index, (before, after) in enumerate(zip(data, output)) if before != after
    ]
    expected_changed = [offset + 2 for offset in offsets]
    if changed != expected_changed:
        raise AssertionError(
            f"补丁字节范围异常：{[hex(value) for value in changed]}"
        )
    return bytes(output), audit


def patch_file(source: Path, destination: Path) -> dict[str, object]:
    if source.resolve() == destination.resolve():
        raise ModifierPatchError("禁止覆盖输入修改器。")
    data = source.read_bytes()
    input_hash = sha256_bytes(data)
    if len(data) != EXPECTED_INPUT_SIZE or input_hash != EXPECTED_INPUT_SHA256:
        raise ModifierPatchError(
            "输入 EXE 不是已审计版本。"
            f"\n实际大小：{len(data)}"
            f"\n实际 SHA-256：{input_hash}"
        )
    if data[:2] != b"MZ" or data[0x80:0x84] != b"PE\0\0":
        raise ModifierPatchError("输入不是预期的 PE 可执行文件。")

    output, patches = patch_modifier_bytes(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)
    output_hash = sha256_bytes(output)
    record: dict[str, object] = {
        "source": str(source),
        "destination": str(destination),
        "inputSize": len(data),
        "inputSha256": input_hash,
        "outputSize": len(output),
        "outputSha256": output_hash,
        "patchCount": len(patches),
        "differentByteCount": len(patches),
        "scope": "expanded-ROM active CHR base only",
        "patches": patches,
    }
    record_path = destination.with_suffix(destination.suffix + ".patch.json")
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将已审计的旧修改器 CHR 起点从 0x80010 改为 0x100010。"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    record = patch_file(args.input, args.output)
    print(f"output: {record['destination']}")
    print(f"size:   {record['outputSize']}")
    print(f"sha256: {record['outputSha256']}")
    print(f"patches:{record['patchCount']}")


if __name__ == "__main__":
    main()
