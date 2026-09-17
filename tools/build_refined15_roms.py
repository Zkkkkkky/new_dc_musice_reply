"""Expand both DC ROM variants and bridge the 15 refined NSF tracks.

The original 512 KiB PRG is immutable.  The original CHR remains at its old
file offsets as a PRG shadow and is copied once more to the active CHR region,
matching the expansion layout used by ``DC_kuorong.nes``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections import deque
from pathlib import Path

from capstone import CS_ARCH_MOS65XX, CS_MODE_MOS65XX_6502, Cs
from capstone.mos65xx import MOS65XX_OP_MEM


ROOT = Path(__file__).resolve().parent.parent
ASM_DIR = ROOT / "src" / "asm"
BUILD_DIR = ROOT / "build" / "refined15"
DIST_DIR = ROOT / "dist" / "roms"
NSF_DIR = ROOT / "assets" / "music" / "01 精修通用驱动（F000-F100-F160）"

SOURCE_ROMS = {
    "新DC上": (
        DIST_DIR / "新DC上.nes",
        "34A669879A1310045FBF15A916B86FBCDA765B3A1B39E799D5A76A16D03BB6EF",
    ),
    "新DC下": (
        DIST_DIR / "新DC下.nes",
        "C623BBA0AE07AE3226A2AF09B1EAB1E42DB36EE3D8865D3DB20D3BF657C38CEC",
    ),
}

TRACKS = (
    ("Alone in the Wind - 精修.nsf", 0x94, 0x14),
    ("Awake! Zeorymer - 冥王.nsf", 0x95, 0x15),
    ("Beyond the Time -逆袭的夏亚精修.nsf", 0xA5, 0x22),
    ("Cherry Blossom Illusion - 樱花精修.nsf", 0x96, 0x16),
    ("Dark Prison - 白河愁精修2.nsf", 0x97, 0x17),
    ("Doomsday - 精修.nsf", 0x98, 0x18),
    ("Fairy Dang-Sing - 精修.nsf", 0x99, 0x19),
    ("Flapper Girl - 琉妮精修.nsf", 0x9A, 0x1A),
    ("From the Aqueous Star with Love - Z高达精修.nsf", 0x9B, 0x1B),
    ("It's Not Anime - zz高达精修.nsf", 0x9C, 0x1C),
    ("JUST COMMUNICATION - 高达EW精修.nsf", 0xA0, 0x1D),
    ("Map Theme - 精修.nsf", 0xA1, 0x1E),
    ("Melua - 精修.nsf", 0xA2, 0x1F),
    ("Moon Knights - 精修.nsf", 0xA3, 0x20),
    ("The Moon Dwellers - 机战J最终关精修.nsf", 0xA4, 0x21),
)

ORIGINAL_TRACK_NAMES = (
    "大卫音乐",
    "盖塔音乐",
    "加代音乐",
    "古莲音乐",
    "吉尔变身音乐",
    "安东音乐",
    "未知音乐2",
    "地球我方音乐",
    "地球敌方音乐",
    "存档音乐",
    "敌方增援音乐2",
    "游戏结束音乐",
    "宇宙我方音乐",
    "敌方增援音乐1",
    "升级音乐",
    "吉尔音乐",
    "瓦尔音乐",
    "宇宙敌方音乐",
    "未知音乐1",
    "通关音乐",
)

HEADER_SIZE = 0x10
BANK_SIZE = 0x2000
SOURCE_ROM_SIZE = 0x0C0010
ROM_SIZE = 0x140010
ORIGINAL_PRG_SIZE = 0x080000
ORIGINAL_CHR_SIZE = 0x040000
EXPANDED_PRG_SIZE = 0x100000
ORIGINAL_PRG_BANKS = 0x40
EXPANDED_PRG_BANKS = 0x80
DATA_BANK_FIRST = 0x65
NATIVE_ENGINE_BANK = 0x74
NATIVE_ANIME_ENGINE_BANK = 0x75
NATIVE_DISPATCH_BANK = 0x76
FAMISTUDIO_ENGINE_BANK = 0x64
STOCK_COPY_BANK = 0x60
SFX_DATA_BANK = 0x77
FIXED_C000_BANK = 0x7E
FIXED_E000_BANK = 0x7F
STOCK_AUDIO_BANK = 0x18
STOCK_FIXED_C000_BANK = 0x3E
STOCK_FIXED_E000_BANK = 0x3F
TRAMPOLINE_CPU_ADDRESS = 0x99AF
TRAMPOLINE_BANK_OFFSET = TRAMPOLINE_CPU_ADDRESS - 0x8000
HANDOFF_CPU_ADDRESS = 0x99EC
HANDOFF_BANK_OFFSET = HANDOFF_CPU_ADDRESS - 0x8000
FIXED_E000_AUDIO_OPERANDS = (0xFA84, 0xFADE)

ASM_STEMS = (
    "dc_dual_audio_trampoline",
    "dc_refined15_audio_handoff",
    "dc_refined15_two_engine_bridge",
    "dc_refined15_dispatcher",
    "dc_refined15_native_wrapper",
    "dc_refined15_sfx_bank",
)
ASM_EXPECTED = {
    "dc_dual_audio_trampoline": (29, "06D56D2CD5BD8194EA08C3741470D726E8A498F12A642F6A6A113A8B7C899932"),
    "dc_refined15_audio_handoff": (77, "8038D75F560118EA7921C9335C8A73222F3EE6B4EBF22A4408D32D8BF883E9B2"),
    "dc_refined15_two_engine_bridge": (252, "B4A5B0427B562CA1938B541A6D8BD9EFCA25A76F0B52C60FBD6F184234836684"),
    "dc_refined15_dispatcher": (45, "0F6C022A7F4BB5F8EFE018ACCC4F6DF0917A3E09C5D763DCECDACB669EF3A85E"),
    "dc_refined15_native_wrapper": (398, "D8090547A76C1F74C2A4EC393BBB0964BA05931FC6B8E6A9DA978400E1080532"),
    "dc_refined15_sfx_bank": (BANK_SIZE, "9E51C2205004DD457D10C701663CB8B31D61A38B978D8776B088306FCAEB66E5"),
}

DRIVER_BASE = 0xF000
RELOCATED_BASE = 0xB000
DRIVER_SIZE = 0x1000

# These bytes are DMC-only, the removed fifth (DMC) channel slots, or a write-
# only constant.  Runtime probes over all 15 tracks prove the DMC paths are
# never entered.  Removing exactly 14 bytes leaves 150 persistent bytes, which
# fit the certified audio RAM after reserving the four bridge-state bytes.
REMOVED_BSS = {
    0x025C,
    0x0261,
    0x0266,
    0x026B,
    0x0270,
    0x0275,
    0x027A,
    0x027F,
    0x028C,
    0x028E,
    0x0298,
    0x029D,
    0x029E,
    0x029F,
}

# The refined driver indexes several arrays directly with X/Y.  Their members
# must stay contiguous after relocation: mapping individual bytes into the
# available RAM holes made (for example) $0221,x cross from $004B into the
# game's $004C-$0056 interface.  The first Flapper Girl update then read a
# channel-pointer high byte from $004D and looped forever through $006B.
#
# Pack whole arrays/blocks instead.  These blocks cover all 150 retained bytes
# exactly and consume only the previously certified stock-audio-owned ranges.
BSS_BLOCK_LAYOUT = (
    # Large contiguous page-$04 block: five 11-byte channel arrays, seven
    # 3-byte envelope arrays, three 4-byte arrays, and four tonal-channel
    # entries from four of the original 5-byte arrays.
    (0x0200, 0x0237, 0x0400),
    (0x0237, 0x024C, 0x0437),
    (0x024C, 0x0258, 0x044C),
    (0x0258, 0x025C, 0x0458),
    (0x025D, 0x0261, 0x045C),
    (0x0262, 0x0266, 0x0460),
    (0x0267, 0x026B, 0x0464),

    # Contiguous zero-page arrays below the game interface.
    (0x026C, 0x0270, 0x002D),
    (0x0271, 0x0275, 0x0031),
    (0x0276, 0x027A, 0x0035),
    (0x027B, 0x027F, 0x0039),
    (0x0280, 0x028C, 0x003D),
    (0x028D, 0x028E, 0x0049),
    (0x0292, 0x0294, 0x004A),

    # The remaining small arrays fit the two other certified zero-page holes
    # and the four bytes above the bridge-state guard.
    (0x028F, 0x0292, 0x0057),
    (0x02A0, 0x02A4, 0x005A),
    (0x0294, 0x0298, 0x0028),
    (0x0299, 0x029D, 0x046C),
)

# Indexed array widths proven by the driver initialization/update loops after
# the fifth/DMC channel is removed.  Keep this list as a regression oracle for
# future RAM-layout changes.
BSS_INDEXED_ARRAYS = (
    *((base, 11) for base in (0x0200, 0x020B, 0x0216, 0x0221, 0x022C)),
    *((base, 3) for base in (0x0237, 0x023A, 0x023D, 0x0240, 0x0243, 0x0246, 0x0249)),
    *((base, 4) for base in (
        0x024C, 0x0250, 0x0254, 0x0258, 0x025D, 0x0262,
        0x0267, 0x026C, 0x0271, 0x0276, 0x027B, 0x0280,
        0x0284, 0x0288,
    )),
    (0x028F, 3),
)
INIT_REMOVED_STORES = (0xF18C, 0xF1A2, 0xF1A8, 0xF1DD, 0xF2D2)
FOUR_CHANNEL_LIMITS = (0xF1F2, 0xF3A5)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def bank_offset(bank: int) -> int:
    return HEADER_SIZE + bank * BANK_SIZE


def resolve_asm6(explicit: Path | None = None) -> Path:
    candidates = [
        explicit,
        Path(os.environ["ASM6_PATH"]) if os.environ.get("ASM6_PATH") else None,
        Path(found) if (found := shutil.which("asm6_fixed.exe")) else None,
        Path(found) if (found := shutil.which("asm6")) else None,
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "找不到 ASM6。请传 --asm6 <asm6_fixed.exe> 或设置 ASM6_PATH。"
    )


def assemble(asm6: Path, output_dir: Path) -> dict[str, bytes]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, bytes] = {}
    for stem in ASM_STEMS:
        source = ASM_DIR / f"{stem}.asm"
        binary = output_dir / f"{stem}.bin"
        listing = output_dir / f"{stem}.lst"
        result = subprocess.run(
            [str(asm6), source.name, str(binary.resolve()), str(listing.resolve())],
            cwd=ASM_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"ASM6 failed for {source.name}:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        payload = binary.read_bytes()
        expected_size, expected_hash = ASM_EXPECTED[stem]
        if len(payload) != expected_size or digest(payload) != expected_hash:
            raise AssertionError(
                f"{stem} 汇编结果不匹配：{len(payload)} bytes / {digest(payload)}"
            )
        outputs[stem] = payload
    return outputs


def decode_driver(driver: bytes) -> dict[int, object]:
    md = Cs(CS_ARCH_MOS65XX, CS_MODE_MOS65XX_6502)
    md.detail = True
    lows = driver[0x09C5:0x09DA]
    highs = driver[0x09DA:0x09EF]
    jump_targets = [
        low | (high << 8) for low, high in zip(lows, highs, strict=True)
    ]
    todo = deque((0xF100, 0xF160, *jump_targets))
    decoded: dict[int, object] = {}
    while todo:
        pc = todo.popleft()
        while DRIVER_BASE <= pc < DRIVER_BASE + DRIVER_SIZE and pc not in decoded:
            insns = list(md.disasm(driver[pc - DRIVER_BASE:pc - DRIVER_BASE + 3], pc, 1))
            if not insns:
                break
            insn = insns[0]
            decoded[pc] = insn
            next_pc = pc + insn.size
            mnemonic = insn.mnemonic.lower()
            operand = next(
                (op.mem for op in insn.operands if op.type == MOS65XX_OP_MEM),
                None,
            )
            if mnemonic == "jsr":
                if operand is not None:
                    todo.append(operand)
                pc = next_pc
            elif mnemonic == "jmp":
                if operand is not None:
                    todo.append(operand)
                break
            elif mnemonic.startswith("b") and mnemonic not in {"bit", "brk"}:
                if operand is not None:
                    todo.append(operand)
                pc = next_pc
            elif mnemonic in {"rts", "rti", "brk"}:
                break
            else:
                pc = next_pc
    return decoded


def bss_mapping() -> dict[int, int]:
    mapping: dict[int, int] = {}
    for logical_start, logical_end, physical_start in BSS_BLOCK_LAYOUT:
        for offset, logical_address in enumerate(range(logical_start, logical_end)):
            if logical_address in REMOVED_BSS:
                raise AssertionError(
                    f"Removed BSS byte ${logical_address:04X} is in a packed block"
                )
            if logical_address in mapping:
                raise AssertionError(f"Duplicate BSS byte ${logical_address:04X}")
            mapping[logical_address] = physical_start + offset

    expected_logical = {
        address
        for address in range(0x0200, 0x02A4)
        if address not in REMOVED_BSS
    }
    expected_physical = {
        address
        for address in range(0x0028, 0x005E)
        if address != 0x002C and not 0x004C <= address <= 0x0056
    }
    expected_physical.update(
        address
        for address in range(0x0400, 0x0470)
        if not 0x0468 <= address <= 0x046B
    )
    if set(mapping) != expected_logical:
        raise AssertionError(
            (sorted(expected_logical - set(mapping)), sorted(set(mapping) - expected_logical))
        )
    if set(mapping.values()) != expected_physical:
        raise AssertionError(
            (
                sorted(expected_physical - set(mapping.values())),
                sorted(set(mapping.values()) - expected_physical),
            )
        )
    if len(mapping) != 150 or len(set(mapping.values())) != 150:
        raise AssertionError((len(mapping), len(set(mapping.values()))))

    for logical_start, length in BSS_INDEXED_ARRAYS:
        physical_start = mapping[logical_start]
        for offset in range(length):
            if mapping[logical_start + offset] != physical_start + offset:
                raise AssertionError(
                    f"Indexed BSS array ${logical_start:04X} is not contiguous"
                )
    return mapping


def relocate_driver(driver: bytes) -> tuple[bytes, dict[int, int]]:
    if len(driver) != DRIVER_SIZE:
        raise ValueError("Shared driver block is not 4 KiB")
    relocated = bytearray(driver)
    decoded = decode_driver(driver)
    mapping = bss_mapping()

    for pc, insn in decoded.items():
        operand = next(
            (op.mem for op in insn.operands if op.type == MOS65XX_OP_MEM),
            None,
        )
        if operand is None:
            continue
        offset = pc - DRIVER_BASE
        replacement: int | None = None
        if DRIVER_BASE <= operand <= 0xFFFF and insn.size == 3:
            replacement = operand - 0x4000
        elif 0x0200 <= operand <= 0x02A3 and operand in mapping:
            replacement = mapping[operand]
        elif 0x0000 <= operand <= 0x0007:
            replacement = 0x004C + operand

        if replacement is None:
            continue
        if insn.size == 2:
            relocated[offset + 1] = replacement & 0xFF
        elif insn.size == 3:
            relocated[offset + 1:offset + 3] = replacement.to_bytes(2, "little")
        else:
            raise AssertionError((pc, insn.mnemonic, insn.op_str, insn.size))

    # Relocate the 21 event-handler addresses stored as split low/high tables.
    for index in range(21):
        original = driver[0x09C5 + index] | (driver[0x09DA + index] << 8)
        relocated_address = original - 0x4000
        relocated[0x09C5 + index] = relocated_address & 0xFF
        relocated[0x09DA + index] = relocated_address >> 8

    # Eliminate writes to removed globals and stop the update loops before the
    # fifth/DMC channel.  Instruction lengths remain unchanged.
    for pc in INIT_REMOVED_STORES:
        relocated[pc - DRIVER_BASE:pc - DRIVER_BASE + 3] = b"\xEA\xEA\xEA"
    for pc in FOUR_CHANNEL_LIMITS:
        offset = pc - DRIVER_BASE
        if relocated[offset:offset + 2] != b"\xE0\x05":
            raise AssertionError(f"Unexpected CPX at ${pc:04X}")
        relocated[offset + 1] = 0x04

    # The song record still contains five two-byte channel pointers.  Process
    # only the four tonal channels, then skip the unused DMC pointer before
    # reading the tempo pointer.  $F2D6-$F2F9 is an unreferenced stop helper:
    # it is not an NSF entry point, has no reachable caller, and is never hit
    # by the 15-track runtime probes.  Its first ten bytes are reused here.
    if driver[0x02D6:0x02E0] != bytes.fromhex(
        "AA F0 18 20 EF F9 A9 00 8D 00"
    ):
        raise AssertionError("Unexpected bytes in the unused $F2D6 helper")
    tempo_pointer_low = mapping[0x0292]
    expected_channel_loop = (
        bytes.fromhex("E0 05 D0 DF B1 50 8D")
        + tempo_pointer_low.to_bytes(2, "little")
    )
    if relocated[0x029C:0x02A5] != expected_channel_loop:
        raise AssertionError("Unexpected relocated channel-pointer loop")
    relocated[0x029C:0x02A5] = bytes.fromhex(
        "E0 04 F0 36 4C 7F B2 EA EA"
    )
    relocated[0x02D6:0x02E0] = (
        bytes.fromhex("C8 C8 B1 50 8D")
        + tempo_pointer_low.to_bytes(2, "little")
        + bytes.fromhex("4C A5 B2")
    )

    if relocated[0x100:0x103] != bytes.fromhex("0A 0A AA"):
        raise AssertionError("Relocated init entry changed unexpectedly")
    if relocated[0x160:0x164] != bytes.fromhex("20 5D B3 60"):
        raise AssertionError("Relocated play entry is not JSR $B35D / RTS")
    return bytes(relocated), mapping


def read_tracks() -> tuple[list[dict[str, object]], bytes, bytes | None]:
    records: list[dict[str, object]] = []
    shared_driver: bytes | None = None
    anime_chunk: bytes | None = None
    for index, (filename, command, logical_id) in enumerate(TRACKS):
        path = NSF_DIR / filename
        raw = path.read_bytes()
        if raw[:5] != b"NESM\x1a" or raw[0x70:0x78] != bytes(range(1, 8)) + b"\x00":
            raise ValueError(f"Unexpected NSF format: {path}")
        if raw[0x08:0x0E] != bytes.fromhex("00 F0 00 F1 60 F1"):
            raise ValueError(f"Unexpected NSF entry points: {path}")
        payload = raw[0x80:]
        if len(payload) % 0x1000:
            raise ValueError(f"Unaligned NSF payload: {path}")
        chunks = [payload[pos:pos + 0x1000] for pos in range(0, len(payload), 0x1000)]
        if not 2 <= len(chunks) <= 4:
            raise ValueError(f"Unexpected NSF size: {path}")
        if shared_driver is None:
            shared_driver = chunks[0]
        elif chunks[0] != shared_driver:
            raise ValueError(f"Driver block is not shared: {path}")

        data_bank = chunks[1] + (chunks[2] if len(chunks) >= 3 else bytes(0x1000))
        if len(chunks) == 4:
            if index != 9:
                raise ValueError(f"Unexpected third data chunk: {path}")
            anime_chunk = chunks[3]
        records.append(
            {
                "index": index,
                "filename": filename,
                "title": filename.removesuffix(".nsf"),
                "command": command,
                "logicalId": logical_id,
                "dataBank": DATA_BANK_FIRST + index,
                "data": data_bank,
                "nsfSha256": digest(raw),
                "payloadBytes": len(payload),
            }
        )
    if shared_driver is None:
        raise AssertionError("No tracks")
    return records, shared_driver, anime_chunk


def patch_bank(image: bytearray, bank: int, payload: bytes) -> None:
    if len(payload) != BANK_SIZE:
        raise ValueError((bank, len(payload)))
    start = bank_offset(bank)
    image[start:start + BANK_SIZE] = payload


def source_bank(source: bytes, bank: int) -> bytes:
    if not 0 <= bank < ORIGINAL_PRG_BANKS:
        raise ValueError(f"Invalid source bank ${bank:02X}")
    start = bank_offset(bank)
    return source[start:start + BANK_SIZE]


def validate_source(source: bytes, expected_hash: str) -> None:
    if len(source) != SOURCE_ROM_SIZE or source[:4] != b"NES\x1a":
        raise ValueError("Unexpected source ROM size or iNES signature")
    if digest(source) != expected_hash:
        raise ValueError(
            f"Source SHA-256 mismatch: {digest(source)} != {expected_hash}"
        )
    if source[4:8] != bytes.fromhex("20 20 23 C0"):
        raise ValueError("Expected 512 KiB PRG, 256 KiB CHR, Mapper 194")

    audio = source_bank(source, STOCK_AUDIO_BANK)
    if audio[:2] != bytes.fromhex("20 80"):
        raise ValueError("Stock audio pointer is no longer $8020")
    if any(audio[TRAMPOLINE_BANK_OFFSET:TRAMPOLINE_BANK_OFFSET + 0x1D]):
        raise ValueError("Stock trampoline slot is not empty")
    if any(audio[HANDOFF_BANK_OFFSET:HANDOFF_BANK_OFFSET + 0x94]):
        raise ValueError("Stock handoff slot is not empty")

    fixed_e000 = source_bank(source, STOCK_FIXED_E000_BANK)
    for address in FIXED_E000_AUDIO_OPERANDS:
        if fixed_e000[address - 0xE000] != STOCK_AUDIO_BANK:
            raise ValueError(f"Unexpected audio bank operand at ${address:04X}")


def expand_source(source: bytes, assembled: dict[str, bytes]) -> bytearray:
    header = bytearray(source[:HEADER_SIZE])
    original_prg = source[HEADER_SIZE:HEADER_SIZE + ORIGINAL_PRG_SIZE]
    original_chr = source[HEADER_SIZE + ORIGINAL_PRG_SIZE:]

    # Preserve the entire old file body as a prefix: the original CHR becomes
    # inactive PRG banks $40-$5F, and an exact CHR copy is appended after the
    # new 1 MiB PRG.  This is the defining DC_kuorong expansion layout.
    expanded_prg = bytearray(original_prg + original_chr)
    expanded_prg.extend(bytes(EXPANDED_PRG_SIZE - len(expanded_prg)))

    copied_audio = bytearray(source_bank(source, STOCK_AUDIO_BANK))
    copied_audio[:2] = TRAMPOLINE_CPU_ADDRESS.to_bytes(2, "little")
    trampoline = assembled["dc_dual_audio_trampoline"]
    copied_audio[
        TRAMPOLINE_BANK_OFFSET:TRAMPOLINE_BANK_OFFSET + len(trampoline)
    ] = trampoline
    handoff = assembled["dc_refined15_audio_handoff"]
    if len(handoff) > 0x94:
        raise ValueError("Audio handoff no longer fits $99EC-$9A7F")
    copied_audio[HANDOFF_BANK_OFFSET:HANDOFF_BANK_OFFSET + len(handoff)] = handoff
    start = STOCK_COPY_BANK * BANK_SIZE
    expanded_prg[start:start + BANK_SIZE] = copied_audio

    start = FIXED_C000_BANK * BANK_SIZE
    expanded_prg[start:start + BANK_SIZE] = source_bank(
        source, STOCK_FIXED_C000_BANK
    )
    fixed_e000 = bytearray(source_bank(source, STOCK_FIXED_E000_BANK))
    for address in FIXED_E000_AUDIO_OPERANDS:
        fixed_e000[address - 0xE000] = STOCK_COPY_BANK
    start = FIXED_E000_BANK * BANK_SIZE
    expanded_prg[start:start + BANK_SIZE] = fixed_e000

    header[4] = EXPANDED_PRG_SIZE // 0x4000
    return bytearray(bytes(header) + bytes(expanded_prg) + original_chr)


def build_one(
    source: bytes,
    records: list[dict[str, object]],
    driver: bytes,
    anime_chunk: bytes | None,
    assembled: dict[str, bytes],
) -> bytes:
    image = expand_source(source, assembled)

    for record in records:
        patch_bank(image, int(record["dataBank"]), bytes(record["data"]))

    wrapper = assembled["dc_refined15_native_wrapper"]
    if len(wrapper) > 0x300:
        raise ValueError("Native wrapper no longer fits after $BD00")
    normal_engine = bytearray(BANK_SIZE)
    normal_engine[0x1000:0x2000] = driver
    normal_engine[0x1D00:0x1D00 + len(wrapper)] = wrapper
    patch_bank(image, NATIVE_ENGINE_BANK, bytes(normal_engine))

    if anime_chunk is None:
        raise ValueError("It's Not Anime third data chunk is missing")
    anime_engine = bytearray(normal_engine)
    anime_engine[0x0000:0x1000] = anime_chunk
    patch_bank(image, NATIVE_ANIME_ENGINE_BANK, bytes(anime_engine))

    dispatcher = assembled["dc_refined15_dispatcher"]
    dispatch_bank = dispatcher + bytes(BANK_SIZE - len(dispatcher))
    patch_bank(image, NATIVE_DISPATCH_BANK, dispatch_bank)

    bridge = assembled["dc_refined15_two_engine_bridge"]
    if len(bridge) > 0x0B00:
        raise ValueError("Bridge no longer fits at $B500")
    bridge_bank = bytearray(BANK_SIZE)
    bridge_bank[0x1500:0x1500 + len(bridge)] = bridge
    patch_bank(image, FAMISTUDIO_ENGINE_BANK, bytes(bridge_bank))
    patch_bank(image, SFX_DATA_BANK, assembled["dc_refined15_sfx_bank"])

    result = bytes(image)
    validate_output(source, result, assembled)
    return result


def validate_output(
    source: bytes, output: bytes, assembled: dict[str, bytes]
) -> None:
    if len(output) != ROM_SIZE:
        raise AssertionError(f"Unexpected output size: {len(output)}")
    header_changes = [
        index for index, (old, new) in enumerate(zip(source[:16], output[:16]))
        if old != new
    ]
    if header_changes != [4] or output[4] != 0x40:
        raise AssertionError(f"Unexpected header changes: {header_changes}")

    # Hard compatibility gate: every byte at every original file-body offset
    # remains identical, including all original PRG and the retained CHR shadow.
    if output[HEADER_SIZE:len(source)] != source[HEADER_SIZE:]:
        raise AssertionError("Original ROM body changed at an old file offset")
    if output[HEADER_SIZE:HEADER_SIZE + ORIGINAL_PRG_SIZE] != source[
        HEADER_SIZE:HEADER_SIZE + ORIGINAL_PRG_SIZE
    ]:
        raise AssertionError("Original PRG banks $00-$3F changed")

    original_chr = source[HEADER_SIZE + ORIGINAL_PRG_SIZE:]
    if output[HEADER_SIZE + EXPANDED_PRG_SIZE:] != original_chr:
        raise AssertionError("Active CHR copy differs from the source CHR")
    for bank in (0x61, 0x62, 0x63):
        if any(output[bank_offset(bank):bank_offset(bank + 1)]):
            raise AssertionError(f"Removed legacy song bank ${bank:02X} is not empty")
    if any(output[bank_offset(0x78):bank_offset(0x7E)]):
        raise AssertionError("Reserved banks $78-$7D are not empty")

    handoff = assembled["dc_refined15_audio_handoff"]
    stock_start = bank_offset(STOCK_COPY_BANK)
    if output[
        stock_start + HANDOFF_BANK_OFFSET:
        stock_start + HANDOFF_BANK_OFFSET + len(handoff)
    ] != handoff:
        raise AssertionError("FCEUX-safe handoff is missing from bank $60")


def mapping_text(records: list[dict[str, object]]) -> str:
    lines = [
        "新DC上／下：原版20曲＋精修15曲命令表",
        "=======================================",
        "",
        "一、原有20项（原歌曲表 $00-$13）",
        "--------------------------------",
        "列表项  歌曲编号  常规命令  曲目",
    ]
    for list_index, title in enumerate(ORIGINAL_TRACK_NAMES, start=1):
        song_id = list_index - 1
        lines.append(
            f"第{list_index:>2}项   ${song_id:02X}       "
            f"${0x80 + song_id:02X}      {title}"
        )
    lines.extend(
        [
            "",
            "说明：歌曲编号 $01 的常规命令 $81 继续播放原版盖塔音乐。",
            "",
            "二、追加15项（扩展选择编号 $14-$22）",
            "------------------------------------",
            "列表项  扩展编号  实际命令  数据Bank  曲目",
        ]
    )
    appended = [record for record in records if int(record["logicalId"]) >= 0x14]
    for list_index, record in enumerate(
        sorted(appended, key=lambda item: int(item["logicalId"])),
        start=21,
    ):
        lines.append(
            f"第{list_index:>2}项   ${int(record['logicalId']):02X}       "
            f"${int(record['command']):02X}       ${int(record['dataBank']):02X}       "
            f"{record['title']}"
        )
    lines.extend(
        [
            "",
            "三、命令与绑定说明",
            "------------------",
            "$9D-$9F：旧测试版三首 FamiStudio 曲目已删除；桥接器安全吞掉这三个命令。",
            "",
            "新增命令明确跳过 $9D-$9F。扩展编号 $1D-$22 的实际命令是 $A0-$A5，",
            "不能按“$80 + 编号”直接推算；关联角色/地图时应使用上表的“实际命令”列。",
            "Beyond the Time 使用扩展编号 $22、实际命令 $A5；原版 $81 已恢复给盖塔音乐。",
            "本轮交付没有猜测角色/地图绑定；15首均已可由命令触发，等待单独绑定表。",
            "",
            "四、ROM布局与运行约束",
            "----------------------",
            "- 原始 PRG Bank $00-$3F 逐字节不变；原 CHR 在 $40-$5F 保留影子副本。",
            "- $60：原音频 Bank 的扩容副本与桥接入口；$61-$63：清空。",
            "- $64：双引擎桥接代码；不存在旧版第三套音乐引擎。",
            "- $65-$73：15首曲目数据；$74/$75：重定位驱动；$76：Bank切换跳板。",
            "- $77：迁移后的56个原版音效；$78-$7D：保留空白。",
            "- $7E/$7F：扩容后的固定 Bank 副本；1 MiB PRG 后是原 CHR 的活动副本。",
            "- 新曲播放时由轻量音效叠加器继续播放 $00-$37 原版音效。",
            "- 精修驱动带嵌套 NMI 映射恢复保护，入口为 $B100/$B160。",
            "- 交还原引擎前写 $27 到 $5000，清除 FCEUX 的 KT-008 高位锁存器。",
            "",
            "当前状态：静态构建通过；运行时验证结果见 evidence 目录。",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asm6",
        type=Path,
        help="asm6_fixed.exe 路径；也可用 ASM6_PATH 环境变量",
    )
    parser.add_argument(
        "--upper",
        type=Path,
        default=SOURCE_ROMS["新DC上"][0],
        help="新DC上 512 KiB PRG 源 ROM",
    )
    parser.add_argument(
        "--lower",
        type=Path,
        default=SOURCE_ROMS["新DC下"][0],
        help="新DC下 512 KiB PRG 源 ROM",
    )
    parser.add_argument(
        "--allow-modified-input",
        action="store_true",
        help="允许编辑器改过的同布局 ROM；仍执行结构与空闲槽校验",
    )
    parser.add_argument(
        "--no-dist",
        action="store_true",
        help="只写 build/refined15，不复制到 dist/roms",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    asm6 = resolve_asm6(args.asm6)
    assembled = assemble(asm6, BUILD_DIR / "asm")
    records, shared_driver, anime_chunk = read_tracks()
    relocated_driver, mapping = relocate_driver(shared_driver)
    if anime_chunk is None:
        raise ValueError("It's Not Anime third data chunk is missing")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if not args.no_dist:
        DIST_DIR.mkdir(parents=True, exist_ok=True)

    source_paths = {"新DC上": args.upper, "新DC下": args.lower}
    outputs: list[dict[str, object]] = []
    for label, source_path in source_paths.items():
        source = source_path.read_bytes()
        expected_hash = None if args.allow_modified_input else SOURCE_ROMS[label][1]
        validate_source(source, expected_hash or digest(source))
        output = build_one(
            source,
            records,
            relocated_driver,
            anime_chunk,
            assembled,
        )
        name = f"{label}_扩容15曲_未绑定.nes"
        build_path = BUILD_DIR / name
        build_path.write_bytes(output)
        dist_path = DIST_DIR / name
        if not args.no_dist:
            dist_path.write_bytes(output)
        outputs.append({
            "label": label,
            "source": str(source_path.resolve()),
            "sourceBytes": len(source),
            "sourceSha256": digest(source),
            "buildPath": str(build_path.relative_to(ROOT)),
            "distPath": None if args.no_dist else str(dist_path.relative_to(ROOT)),
            "bytes": len(output),
            "sha256": digest(output),
        })

    public_records = [
        {key: value for key, value in record.items() if key != "data"}
        for record in records
    ]
    report = {
        "format": "DC Mapper 194 refined15 two-engine expansion v1",
        "outputs": outputs,
        "roleOrMapBindingsAdded": False,
        "engineInstances": [
            "stock DC engine",
            "relocated refined15 common driver",
        ],
        "removedLegacyCommands": ["0x9D", "0x9E", "0x9F"],
        "tracks": public_records,
        "layout": {
            "originalPrg": "$00-$3F (byte-exact)",
            "retainedChrShadow": "$40-$5F",
            "copiedStockAudio": "$60",
            "clearedLegacySongs": "$61-$63",
            "bridgeOnlyBank": "$64",
            "dataBanks": "$65-$73",
            "relocatedDriverBank": "$74",
            "animeDriverAndThirdDataBank": "$75",
            "transitionBank": "$76",
            "migratedSfxBank": "$77",
            "reservedEmpty": "$78-$7D",
            "fixedBankCopies": "$7E-$7F",
            "activeChr": "$100010-$14000F",
            "relocatedInit": "$B100",
            "relocatedPlay": "$B160",
            "wrapper": "$BD00",
        },
        "ram": {
            "sourceBss": "$0200-$02A3 (164 bytes)",
            "removedDmcOrFifthChannelBytes": [f"0x{address:04X}" for address in sorted(REMOVED_BSS)],
            "persistentBytes": len(mapping),
            "persistentTargets": "$0028-$005D except $002C/$004C-$0056; $0400-$046F except $0468-$046B",
            "transientScratch": "$004C-$0053, saved/restored around every native-driver call",
        },
        "compatibility": {
            "originalAddressBodyPreserved": True,
            "fceuxKt008LatchClear": "STA $5000 with A=$27 before handoff",
            "nativeSfxPolicy": "compact 56-effect overlay while refined music owns APU",
            "targetEmulators": ["Mesen 0.9.9", "FCEUX 2.6.6"],
        },
    }
    (BUILD_DIR / "构建校验.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (BUILD_DIR / "BGM曲目对应表.txt").write_text(
        mapping_text(public_records),
        encoding="utf-8-sig",
    )

    for output in outputs:
        print(
            f"{output['label']}: {output['sha256']}  "
            f"{output['distPath'] or output['buildPath']}"
        )


if __name__ == "__main__":
    main()
