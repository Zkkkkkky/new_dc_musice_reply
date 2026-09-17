"""GUI for copying legacy CHR shadow into expanded-ROM active CHR."""

from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


try:
    from chr_sync_core import (  # type: ignore[import-not-found]
        ChrSyncError,
        analyze_chr_copies,
        save_synchronized_copy,
    )
    from nes_layout import parse_nes_layout  # type: ignore[import-not-found]
except ImportError:
    source_root = Path(__file__).resolve().parents[1]
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from chr_sync.core import ChrSyncError, analyze_chr_copies, save_synchronized_copy
    from title_editor.core import parse_nes_layout


APP_TITLE = "扩容 ROM 全 CHR 旧区→新区同步工具 1.0"
ROM_TYPES = (("NES ROM", "*.nes"), ("所有文件", "*.*"))


class ChrSyncApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("760x430")
        self.root.minsize(700, 400)
        self.source_path: Path | None = None
        self.analysis = None

        self.file_var = tk.StringVar(value="请选择经旧修改器保存的扩容 ROM。")
        self.layout_var = tk.StringVar(value="")
        self.diff_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="源 ROM 始终保留，同步结果只能另存。")

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text="扩容 ROM 全 CHR 同步",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "适用于：旧修改器仍将图形写入 0x080010–0x0C000F。\n"
                "操作：将完整 256 KiB 旧 CHR 影子复制到 0x100010–0x14000F 活动 CHR。"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 14))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="1. 选择 ROM", command=self.open_rom).pack(side=tk.LEFT)
        self.sync_button = ttk.Button(
            buttons,
            text="2. 同步并另存",
            command=self.sync_and_save,
            state=tk.DISABLED,
        )
        self.sync_button.pack(side=tk.LEFT, padx=8)

        info = ttk.LabelFrame(outer, text="检查结果", padding=12)
        info.pack(fill=tk.X, pady=14)
        ttk.Label(info, textvariable=self.file_var, wraplength=690).pack(anchor=tk.W)
        ttk.Label(info, textvariable=self.layout_var).pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(info, textvariable=self.diff_var, foreground="#9A3412").pack(
            anchor=tk.W, pady=(8, 0)
        )

        warning = ttk.LabelFrame(outer, text="不要混用", padding=12)
        warning.pack(fill=tk.X)
        ttk.Label(
            warning,
            text=(
                "只能在“原版旧偏移修改器”保存后使用本工具。\n"
                "如果使用的是已打补丁、直接写入活动 CHR 的修改器，"
                "再做旧→新同步会把新修改覆盖掉。"
            ),
            foreground="#B91C1C",
            justify=tk.LEFT,
            wraplength=690,
        ).pack(anchor=tk.W)

        ttk.Label(outer, textvariable=self.status_var, wraplength=700).pack(
            anchor=tk.W, pady=(14, 0)
        )

    def open_rom(self, path: str | None = None) -> None:
        selected = path or filedialog.askopenfilename(
            title="选择扩容 ROM", filetypes=ROM_TYPES
        )
        if not selected:
            return
        try:
            source = Path(selected)
            data = source.read_bytes()
            layout = parse_nes_layout(data)
            analysis = analyze_chr_copies(data, layout)
        except Exception as error:
            self.source_path = None
            self.analysis = None
            self.sync_button.configure(state=tk.DISABLED)
            messagebox.showerror("无法使用该 ROM", str(error), parent=self.root)
            return

        self.source_path = source
        self.analysis = analysis
        self.file_var.set(str(source))
        self.layout_var.set(
            f"旧 CHR：0x{analysis.shadow_offset:06X}–0x{analysis.shadow_offset + analysis.size - 1:06X}  |  "
            f"活动 CHR：0x{analysis.active_offset:06X}–0x{analysis.active_offset + analysis.size - 1:06X}"
        )
        if analysis.mismatch_count:
            self.diff_var.set(
                f"需同步 {analysis.mismatch_count} 字节；旧区差异范围 "
                f"0x{analysis.first_shadow_difference:06X}–0x{analysis.last_shadow_difference:06X}。"
            )
            self.status_var.set("已就绪。同步时会生成新 ROM，不覆盖当前文件。")
        else:
            self.diff_var.set("旧 CHR 与活动 CHR 完全一致，无需同步。")
            self.status_var.set("当前 ROM 已同步。")
        self.sync_button.configure(state=tk.NORMAL)

    def sync_and_save(self) -> None:
        if self.source_path is None or self.analysis is None:
            return
        if not messagebox.askyesno(
            "确认同步方向",
            "确认将旧 CHR 区域作为权威数据，覆盖活动 CHR？\n\n"
            "只有刚使用原版旧偏移修改器时才应选“是”。",
            parent=self.root,
        ):
            return

        destination = filedialog.asksaveasfilename(
            title="另存同步后的 ROM",
            defaultextension=".nes",
            filetypes=ROM_TYPES,
            initialdir=str(self.source_path.parent),
            initialfile=f"{self.source_path.stem}_CHR已同步.nes",
            confirmoverwrite=True,
        )
        if not destination:
            return
        try:
            analysis, source_hash, output_hash = save_synchronized_copy(
                self.source_path, destination
            )
        except Exception as error:
            messagebox.showerror("同步失败", str(error), parent=self.root)
            return

        self.status_var.set(
            f"已生成：{destination}  |  同步 {analysis.mismatch_count} 字节  |  "
            f"SHA-256 {output_hash}"
        )
        messagebox.showinfo(
            "同步完成",
            f"已将旧 CHR 同步到活动 CHR。\n\n"
            f"实际更新：{analysis.mismatch_count} 字节\n"
            f"源 SHA-256：{source_hash}\n"
            f"输出 SHA-256：{output_hash}\n\n"
            "源 ROM 没有被覆盖。",
            parent=self.root,
        )


def main() -> None:
    root = tk.Tk()
    app = ChrSyncApp(root)
    if len(sys.argv) > 1:
        root.after(50, lambda: app.open_rom(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()

