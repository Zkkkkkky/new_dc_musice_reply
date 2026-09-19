"""Validated fixed-offset transform used by the legacy DC ROM encryptor.

The legacy Easy Language utility moves one two-byte value inside PRG Bank $02
and changes a selector byte in original fixed Bank $3F.  Expanded ROMs execute
from the derived Bank $7F copy, so a compatible transform must update the
selector in both banks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import tempfile


INES_HEADER_SIZE = 0x10
BASE_PRG_SIZE = 0x080000
EXPANDED_PRG_SIZE = 0x100000
EXPECTED_CHR_SIZE = 0x040000
EXPECTED_MAPPER = 194

ACTIVE_PAIR_OFFSET = 0x004012
STORED_PAIR_OFFSET = 0x00401E
ORIGINAL_SELECTOR_OFFSET = 0x07F4C8
EXPANDED_SELECTOR_OFFSET = 0x0FF4C8

POINTER_VALUE = bytes((0x80, 0x9D))
EMPTY_PAIR = b"\x00\x00"
DECRYPTED_SELECTOR = 0x11
ENCRYPTED_SELECTOR = 0x17


class RomCipherError(ValueError):
    """Raised when a ROM or requested transform is unsafe or incompatible."""


class CipherState(str, Enum):
    DECRYPTED = "decrypted"
    ENCRYPTED = "encrypted"
    INCONSISTENT = "inconsistent"


class CipherAction(str, Enum):
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"


@dataclass(frozen=True)
class RomLayout:
    mapper: int
    prg_size: int
    chr_size: int
    expected_file_size: int
    expanded: bool


@dataclass(frozen=True)
class RomAnalysis:
    layout: RomLayout
    state: CipherState
    active_pair: bytes
    stored_pair: bytes
    original_selector: int
    expanded_selector: int | None
    issue: str | None


@dataclass(frozen=True)
class TransformResult:
    action: CipherAction
    before: RomAnalysis
    after: RomAnalysis
    changed_offsets: tuple[int, ...]
    source_sha256: str
    output_sha256: str


@dataclass(frozen=True)
class SaveResult:
    source_path: Path
    destination_path: Path
    transform: TransformResult


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def parse_rom_layout(data: bytes | bytearray) -> RomLayout:
    """Strictly validate the two DC-family Mapper 194 layouts we support."""

    if len(data) < INES_HEADER_SIZE or bytes(data[:4]) != b"NES\x1a":
        raise RomCipherError("\u4e0d\u662f\u6709\u6548\u7684 iNES ROM\uff08\u6587\u4ef6\u5934\u4e0d\u662f NES\\x1A\uff09\u3002")

    flags6 = data[6]
    flags7 = data[7]
    if flags7 & 0x0C == 0x08:
        raise RomCipherError("\u6682\u4e0d\u652f\u6301 NES 2.0 \u6587\u4ef6\u5934\u3002")
    if flags6 & 0x04:
        raise RomCipherError("\u5e26 Trainer \u7684 ROM \u4e0d\u5c5e\u4e8e\u5df2\u9a8c\u8bc1\u7684 DC \u5e03\u5c40\u3002")

    mapper = (flags6 >> 4) | (flags7 & 0xF0)
    prg_size = data[4] * 0x4000
    chr_size = data[5] * 0x2000
    expected_file_size = INES_HEADER_SIZE + prg_size + chr_size

    if mapper != EXPECTED_MAPPER:
        raise RomCipherError(f"\u9700\u8981 Mapper 194\uff0c\u5f53\u524d\u662f Mapper {mapper}\u3002")
    if prg_size not in (BASE_PRG_SIZE, EXPANDED_PRG_SIZE):
        raise RomCipherError(
            "PRG \u5fc5\u987b\u662f 512 KiB \u539f\u7248\u6216 1 MiB \u6269\u5bb9\u7248\uff0c"
            f"\u5f53\u524d\u662f {prg_size // 1024} KiB\u3002"
        )
    if chr_size != EXPECTED_CHR_SIZE:
        raise RomCipherError(
            f"CHR \u5fc5\u987b\u662f 256 KiB\uff0c\u5f53\u524d\u662f {chr_size // 1024} KiB\u3002"
        )
    if len(data) != expected_file_size:
        raise RomCipherError(
            f"\u6587\u4ef6\u5927\u5c0f\u5e94\u4e3a 0x{expected_file_size:X}\uff0c"
            f"\u5f53\u524d\u662f 0x{len(data):X}\uff1b\u4e3a\u907f\u514d\u622a\u65ad\u6216\u635f\u574f\u5df2\u62d2\u7edd\u5904\u7406\u3002"
        )

    expanded = prg_size == EXPANDED_PRG_SIZE
    required_last_offset = (
        EXPANDED_SELECTOR_OFFSET if expanded else ORIGINAL_SELECTOR_OFFSET
    )
    if required_last_offset >= len(data):
        raise RomCipherError("ROM \u957f\u5ea6\u4e0d\u8db3\u4ee5\u5305\u542b\u5fc5\u9700\u7684\u56fa\u5b9a Bank \u504f\u79fb\u3002")

    return RomLayout(
        mapper=mapper,
        prg_size=prg_size,
        chr_size=chr_size,
        expected_file_size=expected_file_size,
        expanded=expanded,
    )


def analyze_rom(data: bytes | bytearray) -> RomAnalysis:
    """Classify a validated ROM without modifying it."""

    layout = parse_rom_layout(data)
    active_pair = bytes(data[ACTIVE_PAIR_OFFSET : ACTIVE_PAIR_OFFSET + 2])
    stored_pair = bytes(data[STORED_PAIR_OFFSET : STORED_PAIR_OFFSET + 2])
    original_selector = data[ORIGINAL_SELECTOR_OFFSET]
    expanded_selector = data[EXPANDED_SELECTOR_OFFSET] if layout.expanded else None
    selectors = (
        (original_selector, expanded_selector)
        if layout.expanded
        else (original_selector,)
    )

    if (
        active_pair == POINTER_VALUE
        and stored_pair == EMPTY_PAIR
        and all(value == DECRYPTED_SELECTOR for value in selectors)
    ):
        state = CipherState.DECRYPTED
        issue = None
    elif (
        active_pair == EMPTY_PAIR
        and stored_pair == POINTER_VALUE
        and all(value == ENCRYPTED_SELECTOR for value in selectors)
    ):
        state = CipherState.ENCRYPTED
        issue = None
    else:
        state = CipherState.INCONSISTENT
        selector_text = ", ".join(f"0x{value:02X}" for value in selectors)
        issue = (
            "\u5173\u952e\u5b57\u8282\u4e0d\u7b26\u5408\u5df2\u9a8c\u8bc1\u7684\u52a0\u5bc6\u6001\u6216\u89e3\u5bc6\u6001\uff1a"
            f"0x4012={active_pair.hex(' ').upper()}\uff0c"
            f"0x401E={stored_pair.hex(' ').upper()}\uff0c"
            f"\u9009\u62e9\u5b57\u8282={selector_text}\u3002"
        )

    return RomAnalysis(
        layout=layout,
        state=state,
        active_pair=active_pair,
        stored_pair=stored_pair,
        original_selector=original_selector,
        expanded_selector=expanded_selector,
        issue=issue,
    )


def expected_changed_offsets(layout: RomLayout) -> tuple[int, ...]:
    offsets = {
        ACTIVE_PAIR_OFFSET,
        ACTIVE_PAIR_OFFSET + 1,
        STORED_PAIR_OFFSET,
        STORED_PAIR_OFFSET + 1,
        ORIGINAL_SELECTOR_OFFSET,
    }
    if layout.expanded:
        offsets.add(EXPANDED_SELECTOR_OFFSET)
    return tuple(sorted(offsets))


def transform_rom(
    data: bytes | bytearray, action: CipherAction | str
) -> tuple[bytes, TransformResult]:
    """Return a safely transformed copy and a byte-level verification report."""

    try:
        requested = action if isinstance(action, CipherAction) else CipherAction(action)
    except ValueError as error:
        raise RomCipherError(f"\u672a\u77e5\u64cd\u4f5c\uff1a{action}") from error

    original = bytes(data)
    before = analyze_rom(original)
    if before.state == CipherState.INCONSISTENT:
        raise RomCipherError(before.issue or "ROM \u5173\u952e\u5b57\u8282\u72b6\u6001\u4e0d\u4e00\u81f4\u3002")
    if requested == CipherAction.ENCRYPT and before.state != CipherState.DECRYPTED:
        raise RomCipherError("ROM \u5df2\u5904\u4e8e\u52a0\u5bc6\u72b6\u6001\uff0c\u62d2\u7edd\u91cd\u590d\u52a0\u5bc6\u3002")
    if requested == CipherAction.DECRYPT and before.state != CipherState.ENCRYPTED:
        raise RomCipherError("ROM \u5df2\u5904\u4e8e\u89e3\u5bc6\u72b6\u6001\uff0c\u62d2\u7edd\u91cd\u590d\u89e3\u5bc6\u3002")

    output = bytearray(original)
    if requested == CipherAction.ENCRYPT:
        output[ACTIVE_PAIR_OFFSET : ACTIVE_PAIR_OFFSET + 2] = EMPTY_PAIR
        output[STORED_PAIR_OFFSET : STORED_PAIR_OFFSET + 2] = POINTER_VALUE
        output[ORIGINAL_SELECTOR_OFFSET] = ENCRYPTED_SELECTOR
        if before.layout.expanded:
            output[EXPANDED_SELECTOR_OFFSET] = ENCRYPTED_SELECTOR
        expected_state = CipherState.ENCRYPTED
    else:
        output[ACTIVE_PAIR_OFFSET : ACTIVE_PAIR_OFFSET + 2] = POINTER_VALUE
        output[STORED_PAIR_OFFSET : STORED_PAIR_OFFSET + 2] = EMPTY_PAIR
        output[ORIGINAL_SELECTOR_OFFSET] = DECRYPTED_SELECTOR
        if before.layout.expanded:
            output[EXPANDED_SELECTOR_OFFSET] = DECRYPTED_SELECTOR
        expected_state = CipherState.DECRYPTED

    changed = tuple(
        index
        for index, (old, new) in enumerate(zip(original, output))
        if old != new
    )
    expected = expected_changed_offsets(before.layout)
    if changed != expected:
        raise RomCipherError(
            "\u4fee\u6539\u8fb9\u754c\u6821\u9a8c\u5931\u8d25\uff1a"
            f"\u9884\u671f {', '.join(f'0x{x:X}' for x in expected)}\uff0c"
            f"\u5b9e\u9645 {', '.join(f'0x{x:X}' for x in changed)}\u3002"
        )

    transformed = bytes(output)
    after = analyze_rom(transformed)
    if after.state != expected_state:
        raise RomCipherError("\u4fee\u6539\u540e\u72b6\u6001\u590d\u6838\u5931\u8d25\u3002")
    if len(transformed) != len(original) or transformed[:INES_HEADER_SIZE] != original[:INES_HEADER_SIZE]:
        raise RomCipherError("\u4fee\u6539\u540e ROM \u5927\u5c0f\u6216 iNES Header \u53d1\u751f\u4e86\u610f\u5916\u53d8\u5316\u3002")

    result = TransformResult(
        action=requested,
        before=before,
        after=after,
        changed_offsets=changed,
        source_sha256=sha256_bytes(original),
        output_sha256=sha256_bytes(transformed),
    )
    return transformed, result


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def save_transformed_copy(
    source_path: str | os.PathLike[str],
    destination_path: str | os.PathLike[str],
    action: CipherAction | str,
) -> SaveResult:
    """Atomically create and verify a new ROM; never overwrite the source."""

    source = Path(source_path)
    destination = Path(destination_path)
    if _same_path(source, destination):
        raise RomCipherError("\u4e3a\u4fdd\u62a4\u6e90 ROM\uff0c\u8bf7\u4f7f\u7528\u65b0\u6587\u4ef6\u540d\u53e6\u5b58\u3002")

    original = source.read_bytes()
    output, transform = transform_rom(original, action)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary.write(output)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass

    written = destination.read_bytes()
    if written != output:
        raise RomCipherError("\u4fdd\u5b58\u540e\u56de\u8bfb\u7ed3\u679c\u4e0e\u5185\u5b58\u4e2d\u7684 ROM \u4e0d\u4e00\u81f4\u3002")
    final_analysis = analyze_rom(written)
    if final_analysis != transform.after:
        raise RomCipherError("\u4fdd\u5b58\u540e ROM \u72b6\u6001\u4e0e\u9884\u671f\u4e0d\u4e00\u81f4\u3002")

    return SaveResult(
        source_path=source,
        destination_path=destination,
        transform=transform,
    )


def read_rom(path: str | os.PathLike[str]) -> tuple[bytes, RomAnalysis]:
    data = Path(path).read_bytes()
    return data, analyze_rom(data)

