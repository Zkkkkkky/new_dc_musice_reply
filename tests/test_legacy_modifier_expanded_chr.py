from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from patch_legacy_modifier_expanded_chr import (  # noqa: E402
    ModifierPatchError,
    NEW_CHR_BASE,
    OLD_CHR_BASE,
    patch_modifier_bytes,
)


class LegacyModifierPatchTests(unittest.TestCase):
    def test_changes_only_one_byte_per_known_constant(self) -> None:
        offsets = (8, 24, 40)
        data = bytearray(b"X" * 64)
        old = struct.pack("<I", OLD_CHR_BASE)
        new = struct.pack("<I", NEW_CHR_BASE)
        for offset in offsets:
            data[offset : offset + 4] = old

        output, audit = patch_modifier_bytes(bytes(data), offsets=offsets)

        self.assertEqual(len(audit), len(offsets))
        for offset in offsets:
            self.assertEqual(output[offset : offset + 4], new)
        changed = [
            index for index, (before, after) in enumerate(zip(data, output)) if before != after
        ]
        self.assertEqual(changed, [offset + 2 for offset in offsets])

    def test_rejects_unexpected_extra_constant(self) -> None:
        offsets = (8,)
        data = bytearray(b"X" * 32)
        old = struct.pack("<I", OLD_CHR_BASE)
        data[8:12] = old
        data[20:24] = old
        with self.assertRaises(ModifierPatchError):
            patch_modifier_bytes(bytes(data), offsets=offsets)


if __name__ == "__main__":
    unittest.main()

