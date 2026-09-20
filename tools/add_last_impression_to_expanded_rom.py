"""Add the ROM-common-driver LAST IMPRESSION NSF to a refined-15 ROM.

The input is never overwritten.  The new track uses command $A6, logical ID
$23, and data Bank $78.  Existing music data, original PRG, both CHR copies,
the stock engine, and the common relocated driver remain byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from build_refined15_roms import relocate_driver


ROOT = Path(__file__).resolve().parent.parent
ASM_DIR = ROOT / "src" / "asm"
DEFAULT_NSF = (
    ROOT
    / "assets"
    / "music"
    / "01 精修通用驱动（F000-F100-F160）"
    / "LAST IMPRESSION - 高达W精修（ROM同引擎版）.nsf"
)
DEFAULT_BUILD_DIR = ROOT / "build" / "refined16"

HEADER_SIZE = 0x10
BANK_SIZE = 0x2000
ROM_SIZE = 0x140010
BRIDGE_BANK = 0x64
BRIDGE_OFFSET = 0x1500
STOCK_COPY_BANK = 0x60
TRAMPOLINE_CPU_ADDRESS = 0x99AF
TRAMPOLINE_OFFSET = 0x19AF
HANDOFF_OFFSET = 0x19EC
ENGINE_BANKS = (0x74, 0x75)
WRAPPER_OFFSET = 0x1D00
DISPATCH_BANK = 0x76
DATA_BANK = 0x78

OLD_BRIDGE_LENGTH = 208
OLD_BRIDGE_SHA256 = "AD26413D706C91CCD3F9D536D6D2A6D91399DF3C0E258A1575CC6296DCF74EFB"
OLD_WRAPPER_LENGTH = 365
OLD_WRAPPER_SHA256 = "A8E77BDB6BBD0B6F80DC14168C6194AF3BED5B3B0D8286A6FF07CD6AD1231E80"
DISPATCH_LENGTH = 45
DISPATCH_SHA256 = "0F6C022A7F4BB5F8EFE018ACCC4F6DF0917A3E09C5D763DCECDACB669EF3A85E"
TRAMPOLINE_LENGTH = 29
TRAMPOLINE_SHA256 = "06D56D2CD5BD8194EA08C3741470D726E8A498F12A642F6A6A113A8B7C899932"
HANDOFF_LENGTH = 77
HANDOFF_SHA256 = "8038D75F560118EA7921C9335C8A73222F3EE6B4EBF22A4408D32D8BF883E9B2"

# Locked after assembling the two source files with FamiStudio 4.5.3 asm6_fixed.
NEW_BRIDGE_LENGTH = 208
NEW_BRIDGE_SHA256 = "662229F95D111D428B56CDA28066E4CA936C0B80D25C83437ECD0FEAF27B9667"
NEW_WRAPPER_LENGTH = 373
NEW_WRAPPER_SHA256 = "AC3726C89D190AB551C6251AFD100F9E4A30DD506393C1A482603FA88BE075D0"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def bank_offset(bank: int) -> int:
    return HEADER_SIZE + bank * BANK_SIZE


def bank(image: bytes, index: int) -> bytes:
    start = bank_offset(index)
    return image[start:start + BANK_SIZE]


def resolve_asm6(explicit: Path | None) -> Path:
    if explicit is not None and explicit.is_file():
        return explicit.resolve()
    raise FileNotFoundError("请传入 --asm6 <FamiStudio asm6_fixed.exe 路径>")


def assemble_one(asm6: Path, stem: str, output_dir: Path) -> bytes:
    output_dir.mkdir(parents=True, exist_ok=True)
    binary = output_dir / f"{stem}.bin"
    listing = output_dir / f"{stem}.lst"
    # asm6_fixed is an ANSI program.  Repo-relative output paths avoid passing
    # the workspace's Chinese absolute path through its narrow argv parser.
    binary_arg = os.path.relpath(binary.resolve(), ASM_DIR)
    listing_arg = os.path.relpath(listing.resolve(), ASM_DIR)
    subprocess.run(
        [str(asm6), f"{stem}.asm", binary_arg, listing_arg],
        cwd=ASM_DIR,
        check=True,
    )
    return binary.read_bytes()


def validate_locked_binary(
    label: str, payload: bytes, expected_length: int, expected_hash: str
) -> None:
    if len(payload) != expected_length or digest(payload) != expected_hash:
        raise ValueError(
            f"{label} 汇编结果未锁定：{len(payload)} bytes / {digest(payload)}"
        )


def validate_nsf(nsf: bytes, common_driver: bytes) -> bytes:
    if len(nsf) != 0x3080 or nsf[:5] != b"NESM\x1a":
        raise ValueError("预期 12,416 字节的 NSF 文件")
    if nsf[8:14] != bytes.fromhex("00 F0 00 F1 60 F1"):
        raise ValueError("NSF 入口不是 $F000/$F100/$F160")
    if nsf[0x80:0x1080] != common_driver:
        raise ValueError("NSF 未使用 ROM 当前的 4 KiB 公共驱动")
    return nsf[0x1080:0x3080]


def validate_input(image: bytes) -> None:
    if len(image) != ROM_SIZE:
        raise ValueError(f"预期 {ROM_SIZE} 字节的扩容 ROM")
    if image[:8] != bytes.fromhex("4E 45 53 1A 40 20 23 C0"):
        raise ValueError("预期 1 MiB PRG + 256 KiB CHR 的 Mapper 194 ROM")

    bridge = bank(image, BRIDGE_BANK)[
        BRIDGE_OFFSET:BRIDGE_OFFSET + OLD_BRIDGE_LENGTH
    ]
    validate_locked_binary("旧桥接器", bridge, OLD_BRIDGE_LENGTH, OLD_BRIDGE_SHA256)
    for engine_bank in ENGINE_BANKS:
        wrapper = bank(image, engine_bank)[
            WRAPPER_OFFSET:WRAPPER_OFFSET + OLD_WRAPPER_LENGTH
        ]
        validate_locked_binary(
            f"旧包装器 Bank ${engine_bank:02X}",
            wrapper,
            OLD_WRAPPER_LENGTH,
            OLD_WRAPPER_SHA256,
        )
    dispatcher = bank(image, DISPATCH_BANK)[:DISPATCH_LENGTH]
    validate_locked_binary(
        "调度器", dispatcher, DISPATCH_LENGTH, DISPATCH_SHA256
    )
    if any(bank(image, DATA_BANK)):
        raise ValueError("Bank $78 不为空，拒绝覆盖")
    if any(image[bank_offset(0x79):bank_offset(0x7E)]):
        raise ValueError("Bank $79-$7D 不为空，布局与预期不符")


def patch_candidate(
    source: bytes,
    song_data: bytes,
    new_bridge: bytes,
    new_wrapper: bytes,
    trampoline: bytes,
    handoff: bytes,
) -> bytes:
    validate_input(source)
    if len(song_data) != BANK_SIZE:
        raise ValueError("新曲数据必须恰好占用一个 8 KiB Bank")
    if len(new_bridge) > 0x0B00:
        raise ValueError("新桥接器超出 Bank $64 的 $B500-$BFFF 槽位")
    if len(new_wrapper) > 0x300:
        raise ValueError("新包装器超出 $BD00-$BFFF 槽位")

    result = bytearray(source)
    stock_start = bank_offset(STOCK_COPY_BANK)
    result[stock_start:stock_start + 2] = TRAMPOLINE_CPU_ADDRESS.to_bytes(
        2, "little"
    )
    result[
        stock_start + TRAMPOLINE_OFFSET:
        stock_start + TRAMPOLINE_OFFSET + len(trampoline)
    ] = trampoline
    result[
        stock_start + HANDOFF_OFFSET:
        stock_start + HANDOFF_OFFSET + 0x94
    ] = bytes(0x94)
    result[
        stock_start + HANDOFF_OFFSET:
        stock_start + HANDOFF_OFFSET + len(handoff)
    ] = handoff

    bridge_start = bank_offset(BRIDGE_BANK) + BRIDGE_OFFSET
    bridge_span = max(OLD_BRIDGE_LENGTH, len(new_bridge))
    if any(source[bridge_start + OLD_BRIDGE_LENGTH:bridge_start + bridge_span]):
        raise ValueError("桥接器扩展槽不为空")
    result[bridge_start:bridge_start + bridge_span] = bytes(bridge_span)
    result[bridge_start:bridge_start + len(new_bridge)] = new_bridge

    wrapper_span = max(OLD_WRAPPER_LENGTH, len(new_wrapper))
    for engine_bank in ENGINE_BANKS:
        wrapper_start = bank_offset(engine_bank) + WRAPPER_OFFSET
        if any(
            source[
                wrapper_start + OLD_WRAPPER_LENGTH:wrapper_start + wrapper_span
            ]
        ):
            raise ValueError(f"Bank ${engine_bank:02X} 包装器扩展槽不为空")
        result[wrapper_start:wrapper_start + wrapper_span] = bytes(wrapper_span)
        result[wrapper_start:wrapper_start + len(new_wrapper)] = new_wrapper

    data_start = bank_offset(DATA_BANK)
    result[data_start:data_start + BANK_SIZE] = song_data
    return bytes(result)


def validate_output(
    source: bytes,
    output: bytes,
    song_data: bytes,
    new_bridge: bytes,
    new_wrapper: bytes,
    trampoline: bytes,
    handoff: bytes,
) -> dict[str, object]:
    if len(output) != len(source):
        raise AssertionError("ROM 大小发生变化")
    if output[:HEADER_SIZE] != source[:HEADER_SIZE]:
        raise AssertionError("iNES 头发生变化")
    if output[bank_offset(0x00):bank_offset(0x60)] != source[
        bank_offset(0x00):bank_offset(0x60)
    ]:
        raise AssertionError("Bank $00-$5F 发生非预期变化")
    if output[bank_offset(0x61):bank_offset(0x64)] != source[
        bank_offset(0x61):bank_offset(0x64)
    ]:
        raise AssertionError("Bank $61-$63 发生非预期变化")
    if output[bank_offset(0x65):bank_offset(0x74)] != source[
        bank_offset(0x65):bank_offset(0x74)
    ]:
        raise AssertionError("原 15 曲数据 Bank $65-$73 发生变化")
    if output[bank_offset(0x79):] != source[bank_offset(0x79):]:
        raise AssertionError("Bank $79 之后或活动 CHR 发生变化")
    if bank(output, DATA_BANK) != song_data:
        raise AssertionError("Bank $78 新曲数据不匹配")
    clear_latch = bytes.fromhex("A9 27 8D 00 50")
    if bank(output, STOCK_COPY_BANK).count(clear_latch) != 2:
        raise AssertionError("Bank $60 未包含两处 FCEUX $5000=$27 清锁")

    stock_start = bank_offset(STOCK_COPY_BANK)
    allowed = set(range(stock_start, stock_start + 2))
    allowed.update(range(
        stock_start + TRAMPOLINE_OFFSET,
        stock_start + TRAMPOLINE_OFFSET + len(trampoline),
    ))
    allowed.update(range(
        stock_start + HANDOFF_OFFSET,
        stock_start + HANDOFF_OFFSET + 0x94,
    ))
    allowed.update(range(
        bank_offset(BRIDGE_BANK) + BRIDGE_OFFSET,
        bank_offset(BRIDGE_BANK) + BRIDGE_OFFSET
        + max(OLD_BRIDGE_LENGTH, len(new_bridge)),
    ))
    for engine_bank in ENGINE_BANKS:
        start = bank_offset(engine_bank) + WRAPPER_OFFSET
        allowed.update(range(start, start + max(OLD_WRAPPER_LENGTH, len(new_wrapper))))
    allowed.update(range(bank_offset(DATA_BANK), bank_offset(DATA_BANK + 1)))
    unexpected = [
        index
        for index, (old, new) in enumerate(zip(source, output))
        if old != new and index not in allowed
    ]
    if unexpected:
        raise AssertionError(f"发现非预期修改：${unexpected[0]:X}")

    return {
        "sourceBytes": len(source),
        "sourceSha256": digest(source),
        "outputBytes": len(output),
        "outputSha256": digest(output),
        "command": "0xA6",
        "logicalId": "0x23",
        "dataBank": "0x78",
        "songDataSha256": digest(song_data),
        "fceuxLatchClears": 2,
        "bridgeBytes": len(new_bridge),
        "bridgeSha256": digest(new_bridge),
        "wrapperBytes": len(new_wrapper),
        "wrapperSha256": digest(new_wrapper),
        "changedBytes": sum(a != b for a, b in zip(source, output)),
        "preserved": [
            "header",
            "original PRG and CHR shadow",
            "existing 15 song data banks $65-$73",
            "relocated common driver",
            "dispatcher and SFX bank",
            "fixed banks and active CHR",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="已有扩容 15 曲 ROM")
    parser.add_argument("--output", type=Path, required=True, help="新候选 ROM")
    parser.add_argument("--nsf", type=Path, default=DEFAULT_NSF)
    parser.add_argument("--asm6", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_BUILD_DIR / "LAST_IMPRESSION_构建校验.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    asm6 = resolve_asm6(args.asm6)
    new_bridge = assemble_one(
        asm6, "dc_refined16_two_engine_bridge", DEFAULT_BUILD_DIR / "asm"
    )
    new_wrapper = assemble_one(
        asm6, "dc_refined16_native_wrapper", DEFAULT_BUILD_DIR / "asm"
    )
    trampoline = assemble_one(
        asm6, "dc_dual_audio_trampoline", DEFAULT_BUILD_DIR / "asm"
    )
    handoff = assemble_one(
        asm6, "dc_refined15_audio_handoff", DEFAULT_BUILD_DIR / "asm"
    )
    validate_locked_binary(
        "新桥接器", new_bridge, NEW_BRIDGE_LENGTH, NEW_BRIDGE_SHA256
    )
    validate_locked_binary(
        "新包装器", new_wrapper, NEW_WRAPPER_LENGTH, NEW_WRAPPER_SHA256
    )
    validate_locked_binary(
        "音频入口跳板", trampoline, TRAMPOLINE_LENGTH, TRAMPOLINE_SHA256
    )
    validate_locked_binary(
        "音频交还代码", handoff, HANDOFF_LENGTH, HANDOFF_SHA256
    )

    source = args.input.read_bytes()
    nsf = args.nsf.read_bytes()
    common_driver = bank(source, 0x74)[0x1000:0x2000]
    # $BD00-$BFFF is occupied by the wrapper; compare the preserved driver
    # portion and use the versioned NSF page for the full 4 KiB identity gate.
    reference_driver = next(
        (ROOT / "assets" / "music" / "01 精修通用驱动（F000-F100-F160）").glob(
            "Alone in the Wind*.nsf"
        )
    ).read_bytes()[0x80:0x1080]
    relocated_driver, _ = relocate_driver(reference_driver)
    if common_driver[:0x0D00] != relocated_driver[:0x0D00]:
        raise ValueError("ROM Bank $74 的共用驱动与项目基准不符")
    song_data = validate_nsf(nsf, reference_driver)
    output = patch_candidate(
        source, song_data, new_bridge, new_wrapper, trampoline, handoff
    )
    report = validate_output(
        source,
        output,
        song_data,
        new_bridge,
        new_wrapper,
        trampoline,
        handoff,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
