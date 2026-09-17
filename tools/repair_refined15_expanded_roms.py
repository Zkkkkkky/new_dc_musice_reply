"""Repair timing and RAM hazards in already-modified refined15 ROMs.

This tool deliberately starts from an expanded user ROM.  It replaces only
the copied audio entry, bridge, relocated engines, dispatcher, and SFX bank;
the original-address body, both CHR copies, the 15 song-data banks, and any
gameplay/editor changes remain byte-exact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_refined15_roms as builder


ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build" / "refined15-repair"
DIST_DIR = ROOT / "dist" / "roms"

LEGACY_EXPANSION_HASHES = {
    # Formal v1 expansion.
    "36931CECD8487BF01EC03B397A88221EE381F0CE7C852716DFC5E3AB22196E65",
    # User build with the two $5000 clears and four $5FF8 operands disabled.
    "FE9E9107889A191A6C10C48A14EBF5E5E6B33DDB36C2503058226AC2A4A37402",
}


def validate_expanded(source: bytes) -> None:
    if len(source) != builder.ROM_SIZE or source[:4] != b"NES\x1a":
        raise ValueError("Unexpected expanded ROM size or iNES signature")
    if source[4:8] != bytes.fromhex("40 20 23 C0"):
        raise ValueError("Expected 1 MiB PRG, 256 KiB CHR, Mapper 194")
    expansion = source[0x0C0010:0x100010]
    expansion_hash = builder.digest(expansion)
    if expansion_hash not in LEGACY_EXPANSION_HASHES:
        raise ValueError(
            "Expansion payload is not a known refined15 v1 layout: "
            f"{expansion_hash}"
        )


def runtime_banks(
    assembled: dict[str, bytes],
    relocated_driver: bytes,
    anime_chunk: bytes,
) -> dict[int, bytes]:
    wrapper = assembled["dc_refined15_native_wrapper"]
    if len(wrapper) > 0x300:
        raise ValueError("Native wrapper no longer fits after $BD00")
    normal_engine = bytearray(builder.BANK_SIZE)
    normal_engine[0x1000:0x2000] = relocated_driver
    normal_engine[0x1D00:0x1D00 + len(wrapper)] = wrapper

    anime_engine = bytearray(normal_engine)
    anime_engine[0:0x1000] = anime_chunk

    dispatcher = assembled["dc_refined15_dispatcher"]
    dispatch_bank = dispatcher + bytes(builder.BANK_SIZE - len(dispatcher))

    bridge = assembled["dc_refined15_two_engine_bridge"]
    if len(bridge) > 0x0B00:
        raise ValueError("Bridge no longer fits at $B500")
    bridge_bank = bytearray(builder.BANK_SIZE)
    bridge_bank[0x1500:0x1500 + len(bridge)] = bridge

    return {
        builder.FAMISTUDIO_ENGINE_BANK: bytes(bridge_bank),
        builder.NATIVE_ENGINE_BANK: bytes(normal_engine),
        builder.NATIVE_ANIME_ENGINE_BANK: bytes(anime_engine),
        builder.NATIVE_DISPATCH_BANK: dispatch_bank,
        builder.SFX_DATA_BANK: assembled["dc_refined15_sfx_snapshots"],
    }


def repair_one(
    source: bytes,
    assembled: dict[str, bytes],
    banks: dict[int, bytes],
) -> tuple[bytes, dict[str, int | None]]:
    validate_expanded(source)
    output = bytearray(source)
    allowed_ranges: list[tuple[int, int]] = []

    stock_start = builder.bank_offset(builder.STOCK_COPY_BANK)
    output[stock_start:stock_start + 2] = builder.TRAMPOLINE_CPU_ADDRESS.to_bytes(
        2, "little"
    )
    allowed_ranges.append((stock_start, stock_start + 2))

    trampoline = assembled["dc_dual_audio_trampoline"]
    tramp_start = stock_start + builder.TRAMPOLINE_BANK_OFFSET
    output[tramp_start:tramp_start + len(trampoline)] = trampoline
    allowed_ranges.append((tramp_start, tramp_start + len(trampoline)))

    handoff = assembled["dc_refined15_audio_handoff"]
    if len(handoff) > 0x94:
        raise ValueError("Audio handoff no longer fits $99EC-$9A7F")
    handoff_start = stock_start + builder.HANDOFF_BANK_OFFSET
    output[handoff_start:handoff_start + 0x94] = bytes(0x94)
    output[handoff_start:handoff_start + len(handoff)] = handoff
    allowed_ranges.append((handoff_start, handoff_start + 0x94))

    for bank, payload in banks.items():
        builder.patch_bank(output, bank, payload)
        start = builder.bank_offset(bank)
        allowed_ranges.append((start, start + builder.BANK_SIZE))

    result = bytes(output)
    changed = [index for index, pair in enumerate(zip(source, result)) if pair[0] != pair[1]]
    if any(
        not any(start <= index < end for start, end in allowed_ranges)
        for index in changed
    ):
        raise AssertionError("Repair changed a byte outside the approved runtime ranges")
    if result[:0x0C0010] != source[:0x0C0010]:
        raise AssertionError("Original-address ROM body changed")
    if result[0x100010:] != source[0x100010:]:
        raise AssertionError("Active CHR changed")
    if result[builder.bank_offset(0x65):builder.bank_offset(0x74)] != source[
        builder.bank_offset(0x65):builder.bank_offset(0x74)
    ]:
        raise AssertionError("15-track song-data banks changed")

    return result, {
        "count": len(changed),
        "firstOffset": changed[0] if changed else None,
        "lastOffset": changed[-1] if changed else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm6", type=Path, required=True)
    parser.add_argument("--upper-expanded", type=Path, required=True)
    parser.add_argument("--lower-expanded", type=Path, required=True)
    parser.add_argument("--no-dist", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    assembled = builder.assemble(
        builder.resolve_asm6(args.asm6), BUILD_DIR / "asm"
    )
    assembled["dc_refined15_sfx_snapshots"] = builder.convert_sfx_to_snapshots(
        assembled["dc_refined15_sfx_bank"]
    )
    _, shared_driver, anime_chunk = builder.read_tracks()
    relocated_driver, mapping = builder.relocate_driver(shared_driver)
    if anime_chunk is None:
        raise ValueError("It's Not Anime third data chunk is missing")
    banks = runtime_banks(assembled, relocated_driver, anime_chunk)

    inputs = {
        "新DC上": args.upper_expanded,
        "新DC下": args.lower_expanded,
    }
    outputs: list[dict[str, object]] = []
    for label, source_path in inputs.items():
        source = source_path.read_bytes()
        result, changed = repair_one(source, assembled, banks)
        output_name = f"{label}_扩容15曲_音频时序修复.nes"
        build_path = BUILD_DIR / output_name
        build_path.write_bytes(result)
        dist_path = DIST_DIR / output_name
        if not args.no_dist:
            DIST_DIR.mkdir(parents=True, exist_ok=True)
            dist_path.write_bytes(result)
        outputs.append(
            {
                "label": label,
                "source": str(source_path.resolve()),
                "sourceBytes": len(source),
                "sourceSha256": builder.digest(source),
                "output": str((dist_path if not args.no_dist else build_path).resolve()),
                "outputBytes": len(result),
                "outputSha256": builder.digest(result),
                "changedBytes": changed["count"],
                "firstChangedOffset": changed["firstOffset"],
                "lastChangedOffset": changed["lastOffset"],
                "originalAddressBodySha256": builder.digest(result[:0x0C0010]),
                "activeChrSha256": builder.digest(result[0x100010:]),
                "songDataBanksSha256": builder.digest(
                    result[builder.bank_offset(0x65):builder.bank_offset(0x74)]
                ),
            }
        )

    report = {
        "format": "DC Mapper 194 refined15 timing/RAM repair v2",
        "fixes": [
            "bounded complete-state SFX snapshots",
            "logical $0294-$0295 relocated away from game $0028-$0029",
            "decoded NSF $5FF8 writes redirected to inert $48F8",
            "FCEUX KT-008 $5000 latch clear retained",
        ],
        "ramMapping": {
            "$0294": f"${mapping[0x0294]:04X}",
            "$0295": f"${mapping[0x0295]:04X}",
            "$0296": f"${mapping[0x0296]:04X}",
            "$0297": f"${mapping[0x0297]:04X}",
        },
        "preserved": [
            "iNES header and original-address body $000000-$0C000F",
            "15 song-data banks $65-$73",
            "active CHR $100010-$14000F",
        ],
        "outputs": outputs,
    }
    (BUILD_DIR / "修复校验.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for output in outputs:
        print(f"{output['label']}: {output['outputSha256']}  {output['output']}")


if __name__ == "__main__":
    main()
