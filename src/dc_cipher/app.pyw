"""Windows GUI for the validated DC ROM encrypt/decrypt transform."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    # Use the absolute package import for PyInstaller's one-file entry point.
    # The fallback keeps direct ``python src/dc_cipher/app.pyw`` launches working.
    from dc_cipher.core import (
        ACTIVE_PAIR_OFFSET,
        EXPANDED_SELECTOR_OFFSET,
        ORIGINAL_SELECTOR_OFFSET,
        STORED_PAIR_OFFSET,
        CipherAction,
        CipherState,
        RomAnalysis,
        expected_changed_offsets,
        read_rom,
        save_transformed_copy,
        sha256_bytes,
    )
except ImportError:
    from core import (  # type: ignore[no-redef]
        ACTIVE_PAIR_OFFSET,
        EXPANDED_SELECTOR_OFFSET,
        ORIGINAL_SELECTOR_OFFSET,
        STORED_PAIR_OFFSET,
        CipherAction,
        CipherState,
        RomAnalysis,
        expected_changed_offsets,
        read_rom,
        save_transformed_copy,
        sha256_bytes,
    )


APP_TITLE = "\u65b0DC ROM \u52a0\u5bc6\u89e3\u5bc6\u5de5\u5177 1.0"
ROM_FILE_TYPES = (("NES ROM", "*.nes"), ("\u6240\u6709\u6587\u4ef6", "*.*"))


def state_text(state: CipherState) -> str:
    return {
        CipherState.DECRYPTED: "\u5df2\u89e3\u5bc6",
        CipherState.ENCRYPTED: "\u5df2\u52a0\u5bc6",
        CipherState.INCONSISTENT: "\u72b6\u6001\u4e0d\u4e00\u81f4\uff0c\u5df2\u62d2\u7edd\u4fee\u6539",
    }[state]


class CipherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("780x500")
        self.root.minsize(720, 470)

        self.source_path: Path | None = None
        self.rom_data: bytes | None = None
        self.analysis: RomAnalysis | None = None

        self.file_var = tk.StringVar(value="\u8bf7\u9009\u62e9\u65b0DC Mapper 194 ROM\u3002")
        self.layout_var = tk.StringVar(value="")
        self.bytes_var = tk.StringVar(value="")
        self.state_var = tk.StringVar(value="\u672a\u8bfb\u53d6")
        self.hash_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="\u53ea\u80fd\u53e6\u5b58\u4e3a\u65b0 ROM\uff0c\u6e90\u6587\u4ef6\u4e0d\u4f1a\u88ab\u8986\u76d6\u3002")

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="\u65b0DC ROM \u52a0\u5bc6 / \u89e3\u5bc6", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "\u652f\u6301 512 KiB PRG \u539f\u7248\u4e0e 1 MiB PRG \u6269\u5bb9\u7248\u3002\n"
                "\u6269\u5bb9\u7248\u4f1a\u540c\u6b65\u539f\u59cb Bank $3F \u548c\u8fd0\u884c\u65f6 Bank $7F\u3002"
            ),
        ).pack(anchor=tk.W, pady=(4, 14))

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="1. \u9009\u62e9 ROM", command=self.open_rom).pack(side=tk.LEFT)
        self.encrypt_button = ttk.Button(toolbar, text="2. \u52a0\u5bc6\u5e76\u53e6\u5b58", command=lambda: self.transform(CipherAction.ENCRYPT))
        self.encrypt_button.pack(side=tk.LEFT, padx=8)
        self.decrypt_button = ttk.Button(toolbar, text="2. \u89e3\u5bc6\u5e76\u53e6\u5b58", command=lambda: self.transform(CipherAction.DECRYPT))
        self.decrypt_button.pack(side=tk.LEFT)

        info = ttk.LabelFrame(outer, text="\u4e25\u683c\u68c0\u67e5\u7ed3\u679c", padding=12)
        info.pack(fill=tk.X, pady=(16, 10))
        ttk.Label(info, textvariable=self.file_var, wraplength=720).pack(anchor=tk.W)
        ttk.Label(info, textvariable=self.layout_var).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(info, textvariable=self.bytes_var).pack(anchor=tk.W, pady=(6, 0))
        self.state_label = tk.Label(info, textvariable=self.state_var, anchor="w", font=("Microsoft YaHei UI", 10, "bold"))
        self.state_label.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(info, textvariable=self.hash_var, wraplength=720).pack(anchor=tk.W, pady=(6, 0))

        warning = ttk.LabelFrame(outer, text="\u5b89\u5168\u8fb9\u754c", padding=12)
        warning.pack(fill=tk.X, pady=8)
        ttk.Label(
            warning,
            text=(
                "\u53ea\u63a5\u53d7 Mapper 194\u3001512 KiB/1 MiB PRG\u3001256 KiB CHR \u4e14\u5173\u952e\u5b57\u8282\u5b8c\u5168\u5339\u914d\u7684 ROM\u3002\n"
                "\u4fee\u6539\u4ec5\u9650 5 \u4e2a\uff08\u539f\u7248\uff09\u6216 6 \u4e2a\uff08\u6269\u5bb9\u7248\uff09\u56fa\u5b9a\u504f\u79fb\uff1b\u4fdd\u5b58\u540e\u4f1a\u56de\u8bfb\u590d\u6838\u3002"
            ),
            foreground="#9A3412",
        ).pack(anchor=tk.W)

        ttk.Label(outer, textvariable=self.status_var, wraplength=730).pack(anchor=tk.W, pady=(10, 0))
        self._set_buttons()

    def _set_buttons(self) -> None:
        state = self.analysis.state if self.analysis is not None else None
        self.encrypt_button.configure(state=tk.NORMAL if state == CipherState.DECRYPTED else tk.DISABLED)
        self.decrypt_button.configure(state=tk.NORMAL if state == CipherState.ENCRYPTED else tk.DISABLED)
        color = {
            CipherState.DECRYPTED: "#166534",
            CipherState.ENCRYPTED: "#1D4ED8",
            CipherState.INCONSISTENT: "#B91C1C",
        }.get(state, "#444444")
        self.state_label.configure(foreground=color)

    def open_rom(self, path: str | None = None) -> None:
        selected = path or filedialog.askopenfilename(title="\u9009\u62e9 DC Mapper 194 ROM", filetypes=ROM_FILE_TYPES)
        if not selected:
            return
        try:
            data, analysis = read_rom(selected)
        except Exception as error:
            self.source_path = None
            self.rom_data = None
            self.analysis = None
            self._set_buttons()
            messagebox.showerror("\u65e0\u6cd5\u4f7f\u7528\u8be5 ROM", str(error), parent=self.root)
            return

        self.source_path = Path(selected)
        self.rom_data = data
        self.analysis = analysis
        layout_name = "1 MiB PRG \u6269\u5bb9\u7248" if analysis.layout.expanded else "512 KiB PRG \u539f\u7248"
        selectors = f"0x{analysis.original_selector:02X}"
        if analysis.expanded_selector is not None:
            selectors += f" / 0x{analysis.expanded_selector:02X}"
        self.file_var.set(str(self.source_path))
        self.layout_var.set(f"Mapper 194  |  {layout_name}  |  \u6587\u4ef6\u5927\u5c0f 0x{len(data):X}")
        self.bytes_var.set(
            f"0x{ACTIVE_PAIR_OFFSET:X}: {analysis.active_pair.hex(' ').upper()}  |  "
            f"0x{STORED_PAIR_OFFSET:X}: {analysis.stored_pair.hex(' ').upper()}  |  "
            f"\u9009\u62e9\u5b57\u8282: {selectors}"
        )
        self.state_var.set(state_text(analysis.state))
        self.hash_var.set(f"SHA-256\uff1a{sha256_bytes(data)}")
        self.status_var.set(analysis.issue or "\u5df2\u901a\u8fc7\u4e25\u683c\u6821\u9a8c\uff0c\u53ef\u4ee5\u53e6\u5b58\u8f6c\u6362\u526f\u672c\u3002")
        self._set_buttons()

    def transform(self, action: CipherAction) -> None:
        if self.source_path is None or self.analysis is None:
            return
        action_cn = "\u52a0\u5bc6" if action == CipherAction.ENCRYPT else "\u89e3\u5bc6"
        suffix = "\u5df2\u52a0\u5bc6" if action == CipherAction.ENCRYPT else "\u5df2\u89e3\u5bc6"
        offsets = expected_changed_offsets(self.analysis.layout)
        if not messagebox.askyesno(
            f"\u786e\u8ba4{action_cn}",
            f"\u5c06\u53e6\u5b58\u4e00\u4efd{action_cn}\u540e\u7684 ROM\uff0c\u6e90\u6587\u4ef6\u4fdd\u6301\u4e0d\u53d8\u3002\n\n"
            f"\u9884\u671f\u4fee\u6539 {len(offsets)} \u4e2a\u5b57\u8282\uff1a\n"
            + ", ".join(f"0x{offset:X}" for offset in offsets),
            parent=self.root,
        ):
            return

        selected = filedialog.asksaveasfilename(
            title=f"\u53e6\u5b58{action_cn}\u540e\u7684 ROM",
            defaultextension=".nes",
            filetypes=ROM_FILE_TYPES,
            initialdir=str(self.source_path.parent),
            initialfile=f"{self.source_path.stem}_{suffix}.nes",
            confirmoverwrite=True,
        )
        if not selected:
            return
        try:
            result = save_transformed_copy(self.source_path, selected, action)
        except Exception as error:
            messagebox.showerror(f"{action_cn}\u5931\u8d25", str(error), parent=self.root)
            return

        changed = ", ".join(f"0x{offset:X}" for offset in result.transform.changed_offsets)
        self.status_var.set(f"\u5df2\u751f\u6210\uff1a{selected}  |  SHA-256 {result.transform.output_sha256}")
        messagebox.showinfo(
            f"{action_cn}\u5b8c\u6210",
            f"\u5df2\u751f\u6210\u65b0 ROM\uff0c\u6e90\u6587\u4ef6\u672a\u8986\u76d6\u3002\n\n"
            f"\u5b9e\u9645\u4fee\u6539\uff1a{len(result.transform.changed_offsets)} \u5b57\u8282\n"
            f"\u504f\u79fb\uff1a{changed}\n"
            f"SHA-256\uff1a{result.transform.output_sha256}",
            parent=self.root,
        )


def _run_self_test(arguments: list[str]) -> int:
    """Exercise the frozen core pipeline without opening a GUI window."""

    if len(arguments) != 4:
        return 2
    source_path = Path(arguments[0])
    encrypted_path = Path(arguments[1])
    decrypted_path = Path(arguments[2])
    report_path = Path(arguments[3])
    report: dict[str, object] = {"source": str(source_path), "status": "failed"}
    try:
        source_data, source_analysis = read_rom(source_path)
        encrypted = save_transformed_copy(source_path, encrypted_path, CipherAction.ENCRYPT)
        decrypted = save_transformed_copy(encrypted_path, decrypted_path, CipherAction.DECRYPT)
        decrypted_data, decrypted_analysis = read_rom(decrypted_path)
        if decrypted_data != source_data:
            raise RuntimeError("\u52a0\u5bc6\u540e\u518d\u89e3\u5bc6\u672a\u9010\u5b57\u8282\u6062\u590d\u6e90 ROM\u3002")
        report.update(
            {
                "status": "passed",
                "expanded": source_analysis.layout.expanded,
                "sourceState": source_analysis.state.value,
                "encryptedState": encrypted.transform.after.state.value,
                "decryptedState": decrypted_analysis.state.value,
                "changedOffsets": [f"0x{x:X}" for x in encrypted.transform.changed_offsets],
                "sourceSha256": sha256_bytes(source_data),
                "encryptedSha256": encrypted.transform.output_sha256,
                "roundTripSha256": decrypted.transform.output_sha256,
                "roundTripExact": True,
            }
        )
        return_code = 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        return_code = 1
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return return_code


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        raise SystemExit(_run_self_test(sys.argv[2:]))
    root = tk.Tk()
    app = CipherApp(root)
    if len(sys.argv) > 1:
        root.after(50, lambda: app.open_rom(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()
