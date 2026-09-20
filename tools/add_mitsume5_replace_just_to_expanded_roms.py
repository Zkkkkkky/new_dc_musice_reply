"""Replace JUST COMMUNICATION with five Mitsume tracks in two expanded ROMs.

The two user ROMs are read-only inputs.  All original PRG/CHR edits, stock
music, the existing refined tracks, LAST IMPRESSION in the lower ROM, sound
effects, fixed-bank copies, and active CHR are preserved byte-for-byte outside
the explicitly audited expansion-bank slots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASM_DIR = ROOT / "src" / "asm"
MITSUME_DIR = ROOT / "assets" / "music" / "02 三目童子（精修通用驱动）"
REFINED_DIR = ROOT / "assets" / "music" / "01 精修通用驱动（F000-F100-F160）"
DEFAULT_BUILD = ROOT / "build" / "mitsume5_roms"
DEFAULT_DIST = ROOT / "dist" / "roms"

HEADER_SIZE = 0x10
BANK_SIZE = 0x2000
ROM_SIZE = 0x140010
BRIDGE_BANK = 0x64
BRIDGE_OFFSET = 0x1500
DISPATCH_BANK = 0x76
WRAPPER_BANKS = (0x74, 0x75)
WRAPPER_OFFSET = 0x1D00
MAP_ENTRY_OFFSET = 0x1DAD
MAP_EXTENSION_OFFSET = 0x1F00
BOSS_ENGINE_BANK = 0x7B

EXPECTED_INPUTS = {
    "upper": "490DC9C24829827FB52918E1FF53431B047B3C04DE77BDFBCD1745411FE4CFFF",
    "lower": "840E045A09A81CB8A9C58CA51FF9C0060F8E37826F25A58690EDAF598F1ED31C",
}
OLD_RUNTIME = {
    "upper": {
        "bridgeBytes": 208,
        "bridgeSha256": "AD26413D706C91CCD3F9D536D6D2A6D91399DF3C0E258A1575CC6296DCF74EFB",
        "wrapperBytes": 365,
        "wrapperSha256": "A8E77BDB6BBD0B6F80DC14168C6194AF3BED5B3B0D8286A6FF07CD6AD1231E80",
    },
    "lower": {
        "bridgeBytes": 208,
        "bridgeSha256": "662229F95D111D428B56CDA28066E4CA936C0B80D25C83437ECD0FEAF27B9667",
        "wrapperBytes": 373,
        "wrapperSha256": "AC3726C89D190AB551C6251AFD100F9E4A30DD506393C1A482603FA88BE075D0",
    },
}
OLD_DISPATCH_BYTES = 45
OLD_DISPATCH_SHA256 = "0F6C022A7F4BB5F8EFE018ACCC4F6DF0917A3E09C5D763DCECDACB669EF3A85E"
RELOCATED_DRIVER_CORE_SHA256 = (
    "8F9BB2854B75C963E7C6A2075BADE92B4152A04148A8D98F7F76462159035F7B"
)
COMMON_DRIVER_SHA256 = (
    "20C0C421ADCE739DB24D8C9D445FB1FC6052C59668B3405967156833F402D431"
)

NEW_ASM = {
    "dc_mitsume5_upper_bridge": (
        223,
        "AD2100CD33195C7C6C8D0DFABF881F8E81F7BD6DB7EEF971FE43BBE01D3755EC",
    ),
    "dc_mitsume5_lower_bridge": (
        204,
        "790807898DDFBDC334D3CA17A958C4C000D3E9A96A1786588F58C167FBAB49B3",
    ),
    "dc_mitsume5_data_mapper": (
        82,
        "0F7C8DC210FC1B7D2D6709E93A8950CDD92D43957684971338761632E114001C",
    ),
    "dc_mitsume5_dispatcher": (
        53,
        "461AD1AD265EDE62E736769C5C75CCD18D77EEF7766FE9F63807592F1C49353D",
    ),
}

TRACKS = (
    {
        "title": "Stage 5-2",
        "filename": "三目童子 - Stage 5-2（精修通用驱动版）.nsf",
        "command": 0xA0,
        "logicalId": 0x1D,
        "dataBank": 0x6F,
        "engineBank": 0x74,
    },
    {
        "title": "Stage 5-3",
        "filename": "三目童子 - Stage 5-3（精修通用驱动版）.nsf",
        "command": 0xA7,
        "logicalId": 0x24,
        "dataBank": 0x79,
        "engineBank": 0x74,
    },
    {
        "title": "Boss Fight",
        "filename": "三目童子 - Boss Fight（精修通用驱动版）.nsf",
        "command": 0xA8,
        "logicalId": 0x25,
        "dataBank": 0x7A,
        "engineBank": 0x7B,
    },
    {
        "title": "Introduction",
        "filename": "三目童子 - Introduction（精修通用驱动版）.nsf",
        "command": 0xA9,
        "logicalId": 0x26,
        "dataBank": 0x7C,
        "engineBank": 0x74,
    },
    {
        "title": "Ending (Epilogue)",
        "filename": "三目童子 - Ending (Epilogue)（精修通用驱动版）.nsf",
        "command": 0xAA,
        "logicalId": 0x27,
        "dataBank": 0x7D,
        "engineBank": 0x74,
    },
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def bank_offset(index: int) -> int:
    return HEADER_SIZE + index * BANK_SIZE


def bank(image: bytes, index: int) -> bytes:
    start = bank_offset(index)
    return image[start : start + BANK_SIZE]


def assemble_one(asm6: Path, stem: str, output_dir: Path) -> bytes:
    output_dir.mkdir(parents=True, exist_ok=True)
    binary = output_dir / f"{stem}.bin"
    listing = output_dir / f"{stem}.lst"
    binary_arg = os.path.relpath(binary.resolve(), ASM_DIR)
    listing_arg = os.path.relpath(listing.resolve(), ASM_DIR)
    subprocess.run(
        [str(asm6), f"{stem}.asm", binary_arg, listing_arg],
        cwd=ASM_DIR,
        check=True,
    )
    payload = binary.read_bytes()
    expected_bytes, expected_hash = NEW_ASM[stem]
    if len(payload) != expected_bytes or digest(payload) != expected_hash:
        raise ValueError(
            f"{stem} assembly changed: {len(payload)} bytes / {digest(payload)}"
        )
    return payload


def split_nsf(path: Path, common_driver: bytes) -> tuple[bytes, bytes | None, dict[str, object]]:
    raw = path.read_bytes()
    if raw[:5] != b"NESM\x1a" or raw[8:14] != bytes.fromhex(
        "00 F0 00 F1 60 F1"
    ):
        raise ValueError(f"unexpected NSF format: {path}")
    if raw[0x70:0x78] != bytes.fromhex("01 02 03 04 05 06 07 00"):
        raise ValueError(f"unexpected NSF banks: {path}")
    payload = raw[0x80:]
    if len(payload) % 0x1000:
        raise ValueError(f"unaligned NSF: {path}")
    chunks = [payload[pos : pos + 0x1000] for pos in range(0, len(payload), 0x1000)]
    if not 2 <= len(chunks) <= 4 or chunks[0] != common_driver:
        raise ValueError(f"NSF does not use the accepted common driver: {path}")
    data = chunks[1] + (chunks[2] if len(chunks) >= 3 else bytes(0x1000))
    extra = chunks[3] if len(chunks) == 4 else None
    return data, extra, {
        "nsf": str(path),
        "nsfBytes": len(raw),
        "nsfSha256": digest(raw),
        "payloadPages": len(chunks),
        "dataSha256": digest(data),
        "extraPageSha256": digest(extra) if extra is not None else None,
    }


def load_tracks() -> tuple[list[dict[str, object]], bytes, bytes]:
    reference_path = MITSUME_DIR / str(TRACKS[0]["filename"])
    reference_raw = reference_path.read_bytes()
    common_driver = reference_raw[0x80:0x1080]
    if digest(common_driver) != COMMON_DRIVER_SHA256:
        raise ValueError("Mitsume common driver is not the locked ROM driver")
    records: list[dict[str, object]] = []
    boss_extra: bytes | None = None
    for definition in TRACKS:
        data, extra, info = split_nsf(
            MITSUME_DIR / str(definition["filename"]), common_driver
        )
        record = dict(definition)
        record["data"] = data
        record["extra"] = extra
        record.update(info)
        if record["title"] == "Boss Fight":
            if extra is None:
                raise ValueError("Boss Fight third data page is missing")
            boss_extra = extra
        elif extra is not None:
            raise ValueError(f"unexpected extra data page: {record['title']}")
        records.append(record)
    if boss_extra is None:
        raise AssertionError("Boss Fight data was not loaded")
    return records, boss_extra, common_driver


def expected_just_data(common_driver: bytes) -> bytes:
    path = next(REFINED_DIR.glob("JUST COMMUNICATION*.nsf"))
    data, extra, _ = split_nsf(path, common_driver)
    if extra is not None:
        raise ValueError("JUST COMMUNICATION unexpectedly has a third data page")
    return data


def expected_last_data(common_driver: bytes) -> bytes:
    path = next(REFINED_DIR.glob("LAST IMPRESSION*.nsf"))
    data, extra, _ = split_nsf(path, common_driver)
    if extra is not None:
        raise ValueError("LAST IMPRESSION unexpectedly has a third data page")
    return data


def validate_input(
    image: bytes,
    variant: str,
    just_data: bytes,
    last_data: bytes,
) -> None:
    if len(image) != ROM_SIZE or image[:8] != bytes.fromhex(
        "4E 45 53 1A 40 20 23 C0"
    ):
        raise ValueError(f"{variant}: not the expected expanded Mapper 194 ROM")
    if digest(image) != EXPECTED_INPUTS[variant]:
        raise ValueError(f"{variant}: input hash changed: {digest(image)}")
    if image[0x80010:0xC0010] != image[0x100010:0x140010]:
        raise ValueError(f"{variant}: CHR shadow and active CHR differ")
    if any(image[bank_offset(0x61):bank_offset(0x64)]):
        raise ValueError(f"{variant}: reserved banks $61-$63 are not empty")
    if bank(image, 0x6F) != just_data:
        raise ValueError(f"{variant}: Bank $6F is not JUST COMMUNICATION")
    if variant == "upper":
        if any(bank(image, 0x78)):
            raise ValueError("upper: Bank $78 should remain empty")
    elif bank(image, 0x78) != last_data:
        raise ValueError("lower: Bank $78 is not the locked LAST IMPRESSION data")
    if any(image[bank_offset(0x79):bank_offset(0x7E)]):
        raise ValueError(f"{variant}: target banks $79-$7D are not empty")

    runtime = OLD_RUNTIME[variant]
    bridge = bank(image, BRIDGE_BANK)[
        BRIDGE_OFFSET : BRIDGE_OFFSET + int(runtime["bridgeBytes"])
    ]
    if digest(bridge) != runtime["bridgeSha256"]:
        raise ValueError(f"{variant}: bridge does not match the accepted runtime")
    for engine_bank in WRAPPER_BANKS:
        wrapper = bank(image, engine_bank)[
            WRAPPER_OFFSET : WRAPPER_OFFSET + int(runtime["wrapperBytes"])
        ]
        if digest(wrapper) != runtime["wrapperSha256"]:
            raise ValueError(
                f"{variant}: wrapper in Bank ${engine_bank:02X} changed"
            )
        if bank(image, engine_bank)[MAP_ENTRY_OFFSET : MAP_ENTRY_OFFSET + 4] != bytes.fromhex(
            "AD 6B 04 C9"
        ):
            raise ValueError(f"{variant}: native data mapper entry moved")
        if any(bank(image, engine_bank)[MAP_EXTENSION_OFFSET:]):
            raise ValueError(f"{variant}: wrapper extension area is occupied")
    if digest(bank(image, 0x74)[0x1000:0x1D00]) != RELOCATED_DRIVER_CORE_SHA256:
        raise ValueError(f"{variant}: relocated common-driver core changed")
    dispatcher = bank(image, DISPATCH_BANK)[:OLD_DISPATCH_BYTES]
    if digest(dispatcher) != OLD_DISPATCH_SHA256:
        raise ValueError(f"{variant}: dispatcher changed")


def patch_slot(result: bytearray, start: int, old_length: int, payload: bytes) -> None:
    span = max(old_length, len(payload))
    result[start : start + span] = bytes(span)
    result[start : start + len(payload)] = payload


def build_one(
    source: bytes,
    variant: str,
    records: list[dict[str, object]],
    boss_extra: bytes,
    bridge: bytes,
    data_mapper: bytes,
    dispatcher: bytes,
) -> bytes:
    result = bytearray(source)
    runtime = OLD_RUNTIME[variant]
    bridge_start = bank_offset(BRIDGE_BANK) + BRIDGE_OFFSET
    old_bridge_length = int(runtime["bridgeBytes"])
    if any(source[bridge_start + old_bridge_length : bridge_start + len(bridge)]):
        raise ValueError(f"{variant}: bridge growth area is occupied")
    patch_slot(result, bridge_start, old_bridge_length, bridge)

    dispatch_start = bank_offset(DISPATCH_BANK)
    if any(source[dispatch_start + OLD_DISPATCH_BYTES : dispatch_start + len(dispatcher)]):
        raise ValueError(f"{variant}: dispatcher growth area is occupied")
    patch_slot(result, dispatch_start, OLD_DISPATCH_BYTES, dispatcher)

    jump_to_extension = bytes.fromhex("4C 00 BF")
    for engine_bank in WRAPPER_BANKS:
        base = bank_offset(engine_bank)
        result[
            base + MAP_ENTRY_OFFSET : base + MAP_ENTRY_OFFSET + 3
        ] = jump_to_extension
        result[
            base + MAP_EXTENSION_OFFSET : base + MAP_EXTENSION_OFFSET + len(data_mapper)
        ] = data_mapper

    by_title = {str(record["title"]): record for record in records}
    for record in records:
        data_start = bank_offset(int(record["dataBank"]))
        result[data_start : data_start + BANK_SIZE] = bytes(record["data"])

    boss_engine = bytearray(
        result[bank_offset(0x74) : bank_offset(0x74) + BANK_SIZE]
    )
    boss_engine[:0x1000] = boss_extra
    result[
        bank_offset(BOSS_ENGINE_BANK) : bank_offset(BOSS_ENGINE_BANK + 1)
    ] = boss_engine
    return bytes(result)


def validate_output(
    source: bytes,
    output: bytes,
    variant: str,
    records: list[dict[str, object]],
    boss_extra: bytes,
    bridge: bytes,
    data_mapper: bytes,
    dispatcher: bytes,
) -> dict[str, object]:
    if len(output) != len(source) or output[:HEADER_SIZE] != source[:HEADER_SIZE]:
        raise AssertionError(f"{variant}: size or header changed")
    allowed: set[int] = set()
    runtime = OLD_RUNTIME[variant]
    bridge_start = bank_offset(BRIDGE_BANK) + BRIDGE_OFFSET
    allowed.update(
        range(
            bridge_start,
            bridge_start + max(int(runtime["bridgeBytes"]), len(bridge)),
        )
    )
    allowed.update(range(bank_offset(0x6F), bank_offset(0x70)))
    for engine_bank in WRAPPER_BANKS:
        base = bank_offset(engine_bank)
        allowed.update(range(base + MAP_ENTRY_OFFSET, base + MAP_ENTRY_OFFSET + 3))
        allowed.update(
            range(
                base + MAP_EXTENSION_OFFSET,
                base + MAP_EXTENSION_OFFSET + len(data_mapper),
            )
        )
    allowed.update(range(bank_offset(DISPATCH_BANK), bank_offset(DISPATCH_BANK) + len(dispatcher)))
    allowed.update(range(bank_offset(0x79), bank_offset(0x7E)))
    unexpected = [
        index
        for index, (old, new) in enumerate(zip(source, output))
        if old != new and index not in allowed
    ]
    if unexpected:
        raise AssertionError(f"{variant}: unexpected change at file ${unexpected[0]:X}")

    if output[:bank_offset(0x60)] != source[:bank_offset(0x60)]:
        raise AssertionError(f"{variant}: header/original body changed")
    if output[bank_offset(0x61):bank_offset(0x64)] != source[
        bank_offset(0x61):bank_offset(0x64)
    ]:
        raise AssertionError(f"{variant}: reserved $61-$63 changed")
    if output[bank_offset(0x65):bank_offset(0x6F)] != source[
        bank_offset(0x65):bank_offset(0x6F)
    ] or output[bank_offset(0x70):bank_offset(0x74)] != source[
        bank_offset(0x70):bank_offset(0x74)
    ]:
        raise AssertionError(f"{variant}: retained refined-song banks changed")
    if bank(output, 0x78) != bank(source, 0x78):
        raise AssertionError(f"{variant}: Bank $78 changed")
    if output[bank_offset(0x7E):] != source[bank_offset(0x7E):]:
        raise AssertionError(f"{variant}: fixed banks or active CHR changed")
    if bank(output, 0x75)[:0x1000] != bank(source, 0x75)[:0x1000]:
        raise AssertionError(f"{variant}: It's Not Anime extra page changed")
    for engine_bank in WRAPPER_BANKS + (BOSS_ENGINE_BANK,):
        if bank(output, engine_bank)[MAP_ENTRY_OFFSET : MAP_ENTRY_OFFSET + 3] != bytes.fromhex(
            "4C 00 BF"
        ):
            raise AssertionError(f"{variant}: Bank ${engine_bank:02X} mapper hook missing")
        if bank(output, engine_bank)[
            MAP_EXTENSION_OFFSET : MAP_EXTENSION_OFFSET + len(data_mapper)
        ] != data_mapper:
            raise AssertionError(f"{variant}: Bank ${engine_bank:02X} mapper extension mismatch")
    if bank(output, BOSS_ENGINE_BANK)[:0x1000] != boss_extra:
        raise AssertionError(f"{variant}: Boss Fight third page mismatch")
    if bank(output, BOSS_ENGINE_BANK)[0x1000:0x1D00] != bank(output, 0x74)[0x1000:0x1D00]:
        raise AssertionError(f"{variant}: Boss Fight driver core mismatch")
    for record in records:
        if bank(output, int(record["dataBank"])) != record["data"]:
            raise AssertionError(f"{variant}: {record['title']} data mismatch")

    return {
        "variant": variant,
        "sourceBytes": len(source),
        "sourceSha256": digest(source),
        "outputBytes": len(output),
        "outputSha256": digest(output),
        "changedBytes": sum(left != right for left, right in zip(source, output)),
        "preservedBank78": "empty" if variant == "upper" else "LAST IMPRESSION",
        "bridgeBytes": len(bridge),
        "bridgeSha256": digest(bridge),
        "dispatcherBytes": len(dispatcher),
        "dispatcherSha256": digest(dispatcher),
        "dataMapperBytes": len(data_mapper),
        "dataMapperSha256": digest(data_mapper),
        "preserved": [
            "header and original PRG $00-$3F",
            "CHR shadow $40-$5F and active CHR",
            "stock audio copy $60",
            "reserved empty banks $61-$63",
            "existing refined data except replaced Bank $6F",
            "It's Not Anime third page in Bank $75",
            "SFX Bank $77",
            "Bank $78 (empty upper / LAST IMPRESSION lower)",
            "fixed-bank copies $7E-$7F",
        ],
    }


def public_track(record: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in record.items()
        if key not in ("data", "extra")
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upper", type=Path, required=True)
    parser.add_argument("--lower", type=Path, required=True)
    parser.add_argument("--asm6", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--publish", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    asm6 = args.asm6.resolve()
    if not asm6.is_file():
        raise FileNotFoundError(asm6)
    build_dir = args.build_dir.resolve()
    asm_dir = build_dir / "asm"
    upper_bridge = assemble_one(asm6, "dc_mitsume5_upper_bridge", asm_dir)
    lower_bridge = assemble_one(asm6, "dc_mitsume5_lower_bridge", asm_dir)
    data_mapper = assemble_one(asm6, "dc_mitsume5_data_mapper", asm_dir)
    dispatcher = assemble_one(asm6, "dc_mitsume5_dispatcher", asm_dir)
    records, boss_extra, common_driver = load_tracks()
    just_data = expected_just_data(common_driver)
    last_data = expected_last_data(common_driver)

    outputs = []
    for variant, label, path, bridge in (
        ("upper", "新DC上", args.upper.resolve(), upper_bridge),
        ("lower", "新DC下", args.lower.resolve(), lower_bridge),
    ):
        source = path.read_bytes()
        validate_input(source, variant, just_data, last_data)
        output = build_one(
            source,
            variant,
            records,
            boss_extra,
            bridge,
            data_mapper,
            dispatcher,
        )
        validation = validate_output(
            source,
            output,
            variant,
            records,
            boss_extra,
            bridge,
            data_mapper,
            dispatcher,
        )
        filename = f"{label}_三目童子5曲_替换JUST.nes"
        build_path = build_dir / filename
        build_path.parent.mkdir(parents=True, exist_ok=True)
        build_path.write_bytes(output)
        validation["buildPath"] = str(build_path)
        if args.publish:
            dist_path = args.dist_dir.resolve() / filename
            dist_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(build_path, dist_path)
            validation["distPath"] = str(dist_path)
        outputs.append(validation)

    report = {
        "format": "DC Mapper 194 Mitsume 5 replacing JUST COMMUNICATION v1",
        "replaced": {
            "command": "0xA0",
            "logicalId": "0x1D",
            "oldTitle": "JUST COMMUNICATION - 高达EW精修",
            "oldDataBank": "0x6F",
            "newTitle": "Stage 5-2",
        },
        "commands": {
            "0xA0": "Stage 5-2",
            "0xA7": "Stage 5-3",
            "0xA8": "Boss Fight",
            "0xA9": "Introduction",
            "0xAA": "Ending (Epilogue)",
        },
        "commonDriverSha256": digest(common_driver),
        "tracks": [public_track(record) for record in records],
        "outputs": outputs,
        "roleOrMapBindingsAdded": False,
    }
    report_path = build_dir / "构建校验.json"
    report_path.write_text(
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
