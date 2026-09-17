"""Windows GUI for editing the active title CHR in expanded DC ROMs."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from .core import (
        TITLE_BLOCK_SIZE,
        TITLE_PIXEL_HEIGHT,
        TITLE_PIXEL_WIDTH,
        TITLE_TILE_COLUMNS,
        decode_title_pixels,
        encode_title_pixels,
        get_title_copies,
        parse_nes_layout,
        read_rom,
        save_title_copy,
        sha256_bytes,
        set_title_pixel,
    )
except ImportError:
    from core import (  # type: ignore[no-redef]
        TITLE_BLOCK_SIZE,
        TITLE_PIXEL_HEIGHT,
        TITLE_PIXEL_WIDTH,
        TITLE_TILE_COLUMNS,
        decode_title_pixels,
        encode_title_pixels,
        get_title_copies,
        parse_nes_layout,
        read_rom,
        save_title_copy,
        sha256_bytes,
        set_title_pixel,
    )


APP_TITLE = "扩容 ROM 标题编辑器 1.0"
DISPLAY_COLORS = ("#101820", "#536878", "#A7C7D9", "#F4F8FB")
PNG_FILE_TYPES = (("PNG 图片", "*.png"), ("所有文件", "*.*"))
ROM_FILE_TYPES = (("NES ROM", "*.nes"), ("所有文件", "*.*"))


class TitleEditorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(760, 640)

        self.source_path: Path | None = None
        self.rom_data: bytes | None = None
        self.layout = None
        self.copies = None
        self.title_data = bytearray(TITLE_BLOCK_SIZE)
        self.pixels = [0] * (TITLE_PIXEL_WIDTH * TITLE_PIXEL_HEIGHT)
        self.pixel_items: list[int] = []
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []
        self.stroke_before: bytes | None = None
        self.last_painted: tuple[int, int] | None = None
        self.dirty = False

        self.pen_var = tk.IntVar(value=3)
        self.zoom_var = tk.IntVar(value=4)
        self.file_info_var = tk.StringVar(value="请先打开 Mapper 194 ROM")
        self.copy_info_var = tk.StringVar(value="")
        self.pointer_info_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(
            value="左键绘制，右键擦除，中键取色；实际游戏颜色由调色板决定。"
        )

        self._build_menu()
        self._build_ui()
        self._bind_shortcuts()
        self._rebuild_canvas()

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="打开 ROM...", accelerator="Ctrl+O", command=self.open_rom)
        file_menu.add_command(
            label="另存为新 ROM...", accelerator="Ctrl+Shift+S", command=self.save_as
        )
        file_menu.add_separator()
        file_menu.add_command(label="导入 128×112 PNG...", command=self.import_png)
        file_menu.add_command(label="导出 128×112 PNG...", command=self.export_png)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_close)
        menu.add_cascade(label="文件", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="撤销", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="重做", accelerator="Ctrl+Y", command=self.redo)
        menu.add_cascade(label="编辑", menu=edit_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="关于安全保存", command=self.show_safety_help)
        menu.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menu)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="打开 ROM", command=self.open_rom).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="另存新 ROM", command=self.save_as).pack(
            side=tk.LEFT, padx=(6, 14)
        )
        self.active_button = ttk.Button(
            toolbar, text="读取当前生效标题", command=lambda: self.load_title_copy(False)
        )
        self.active_button.pack(side=tk.LEFT)
        self.shadow_button = ttk.Button(
            toolbar, text="读取 CT2 旧偏移修改", command=lambda: self.load_title_copy(True)
        )
        self.shadow_button.pack(side=tk.LEFT, padx=6)

        ttk.Label(outer, textvariable=self.file_info_var).pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(outer, textvariable=self.copy_info_var, foreground="#9A3412").pack(
            anchor=tk.W, pady=(2, 8)
        )

        editor_row = ttk.Frame(outer)
        editor_row.pack(fill=tk.BOTH, expand=True)

        controls = ttk.LabelFrame(editor_row, text="画笔", padding=8)
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        for value, color in enumerate(DISPLAY_COLORS):
            button = tk.Radiobutton(
                controls,
                text=f"色号 {value}",
                variable=self.pen_var,
                value=value,
                indicatoron=False,
                width=8,
                height=2,
                background=color,
                foreground="white" if value < 2 else "black",
                selectcolor=color,
                activebackground=color,
            )
            button.pack(fill=tk.X, pady=2)

        ttk.Separator(controls).pack(fill=tk.X, pady=10)
        ttk.Label(controls, text="缩放").pack(anchor=tk.W)
        zoom = ttk.Combobox(
            controls,
            textvariable=self.zoom_var,
            values=(3, 4, 5, 6),
            width=6,
            state="readonly",
        )
        zoom.pack(anchor=tk.W, pady=(2, 10))
        zoom.bind("<<ComboboxSelected>>", lambda _event: self._rebuild_canvas())

        ttk.Button(controls, text="撤销", command=self.undo).pack(fill=tk.X, pady=2)
        ttk.Button(controls, text="重做", command=self.redo).pack(fill=tk.X, pady=2)
        ttk.Button(controls, text="导入 PNG", command=self.import_png).pack(
            fill=tk.X, pady=(12, 2)
        )
        ttk.Button(controls, text="导出 PNG", command=self.export_png).pack(fill=tk.X, pady=2)

        canvas_frame = ttk.Frame(editor_row)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, background="#202020", highlightthickness=0)
        self.canvas.pack(anchor=tk.NW)
        self.canvas.bind("<ButtonPress-1>", lambda event: self._start_stroke(event, None))
        self.canvas.bind("<B1-Motion>", lambda event: self._continue_stroke(event, None))
        self.canvas.bind("<ButtonRelease-1>", self._end_stroke)
        self.canvas.bind("<ButtonPress-3>", lambda event: self._start_stroke(event, 0))
        self.canvas.bind("<B3-Motion>", lambda event: self._continue_stroke(event, 0))
        self.canvas.bind("<ButtonRelease-3>", self._end_stroke)
        self.canvas.bind("<Button-2>", self._pick_color)
        self.canvas.bind("<Motion>", self._update_pointer_info)

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(bottom, textvariable=self.pointer_info_var).pack(anchor=tk.W)
        ttk.Label(bottom, textvariable=self.status_var).pack(anchor=tk.W, pady=(2, 0))

        self._set_rom_controls(False)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _event: self.open_rom())
        self.root.bind("<Control-Shift-S>", lambda _event: self.save_as())
        self.root.bind("<Control-z>", lambda _event: self.undo())
        self.root.bind("<Control-y>", lambda _event: self.redo())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_rom_controls(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.active_button.configure(state=state)
        self.shadow_button.configure(state=state)

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        return messagebox.askyesno(
            "放弃未保存修改？", "当前标题尚未另存，确定放弃吗？", parent=self.root
        )

    def open_rom(self, path: str | None = None) -> None:
        if not self._confirm_discard():
            return
        selected = path or filedialog.askopenfilename(
            title="打开 DC Mapper 194 ROM", filetypes=ROM_FILE_TYPES
        )
        if not selected:
            return
        try:
            rom_data, layout, copies = read_rom(selected)
        except Exception as error:
            messagebox.showerror("无法打开 ROM", str(error), parent=self.root)
            return

        use_shadow = False
        if layout.expanded and copies.mismatch_count:
            choice = messagebox.askyesnocancel(
                "检测到 CT2 旧偏移修改",
                f"旧 CHR 影子与模拟器实际读取的活动 CHR 相差 "
                f"{copies.mismatch_count} 字节。\n\n"
                "选“是”：载入 CT2 留在旧偏移的修改，可用于修复。\n"
                "选“否”：载入当前模拟器真正使用的标题。\n"
                "选“取消”：不打开。",
                parent=self.root,
            )
            if choice is None:
                return
            use_shadow = choice

        self.source_path = Path(selected)
        self.rom_data = rom_data
        self.layout = layout
        self.copies = copies
        self._set_rom_controls(True)
        self._load_bytes(copies.shadow if use_shadow else copies.active)
        source_description = "CT2 旧偏移影子" if use_shadow else "模拟器活动 CHR"
        self._update_rom_labels(source_description)
        self.status_var.set(
            f"已读取 {source_description}。另存时会同步两份 CHR，不覆盖源 ROM。"
        )

    def _update_rom_labels(self, source_description: str) -> None:
        if self.source_path is None or self.layout is None or self.copies is None:
            return
        variant = "1 MiB PRG 扩容版" if self.layout.expanded else "512 KiB PRG 原版"
        self.file_info_var.set(
            f"{self.source_path.name}  |  Mapper 194  |  {variant}  |  "
            f"活动标题 0x{self.layout.title_active_offset:X}"
        )
        if self.layout.expanded:
            self.copy_info_var.set(
                f"当前编辑源：{source_description}；影子 0x{self.layout.title_shadow_offset:X}，"
                f"两份相差 {self.copies.mismatch_count} 字节。"
            )
        else:
            self.copy_info_var.set(f"当前编辑源：{source_description}。")

    def load_title_copy(self, use_shadow: bool) -> None:
        if self.copies is None or self.layout is None:
            return
        if not self._confirm_discard():
            return
        self._load_bytes(self.copies.shadow if use_shadow else self.copies.active)
        description = "CT2 旧偏移影子" if use_shadow else "模拟器活动 CHR"
        self._update_rom_labels(description)
        self.status_var.set(f"已切换到{description}。")

    def _load_bytes(self, title_bytes: bytes) -> None:
        self.title_data = bytearray(title_bytes)
        self.pixels = decode_title_pixels(self.title_data)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False
        self._refresh_all_pixels()

    def save_as(self) -> None:
        if self.source_path is None:
            messagebox.showinfo("未打开 ROM", "请先打开 ROM。", parent=self.root)
            return
        initial_name = f"{self.source_path.stem}_标题已修改.nes"
        selected = filedialog.asksaveasfilename(
            title="另存为新 ROM",
            defaultextension=".nes",
            filetypes=ROM_FILE_TYPES,
            initialdir=str(self.source_path.parent),
            initialfile=initial_name,
            confirmoverwrite=True,
        )
        if not selected:
            return
        try:
            layout, sha256 = save_title_copy(
                self.source_path, selected, self.title_data, mirror_shadow=True
            )
        except Exception as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return
        self.dirty = False
        self.status_var.set(f"已保存：{selected}  |  SHA-256 {sha256}")
        messagebox.showinfo(
            "保存完成",
            f"已生成新 ROM，源文件未覆盖。\n\n"
            f"活动标题：0x{layout.title_active_offset:X}\n"
            f"旧影子：0x{layout.title_shadow_offset:X}\n"
            f"SHA-256：{sha256}",
            parent=self.root,
        )

    def _start_stroke(self, event: tk.Event, forced_value: int | None) -> None:
        if self.source_path is None:
            return
        self.stroke_before = bytes(self.title_data)
        self.last_painted = None
        self._paint_event(event, self.pen_var.get() if forced_value is None else forced_value)

    def _continue_stroke(self, event: tk.Event, forced_value: int | None) -> None:
        if self.stroke_before is None:
            return
        self._paint_event(event, self.pen_var.get() if forced_value is None else forced_value)

    def _end_stroke(self, _event: tk.Event) -> None:
        if self.stroke_before is not None and self.stroke_before != bytes(self.title_data):
            self.undo_stack.append(self.stroke_before)
            if len(self.undo_stack) > 100:
                del self.undo_stack[0]
            self.redo_stack.clear()
            self.dirty = True
        self.stroke_before = None
        self.last_painted = None

    def _event_pixel(self, event: tk.Event) -> tuple[int, int] | None:
        scale = self.zoom_var.get()
        x = int(event.x) // scale
        y = int(event.y) // scale
        if 0 <= x < TITLE_PIXEL_WIDTH and 0 <= y < TITLE_PIXEL_HEIGHT:
            return x, y
        return None

    def _paint_event(self, event: tk.Event, value: int) -> None:
        point = self._event_pixel(event)
        if point is None or point == self.last_painted:
            return
        self.last_painted = point
        x, y = point
        index = y * TITLE_PIXEL_WIDTH + x
        if self.pixels[index] == value:
            return
        self.pixels[index] = value
        set_title_pixel(self.title_data, x, y, value)
        if self.pixel_items:
            self.canvas.itemconfigure(self.pixel_items[index], fill=DISPLAY_COLORS[value])
        self._update_pointer_info(event)

    def _pick_color(self, event: tk.Event) -> None:
        point = self._event_pixel(event)
        if point is None:
            return
        x, y = point
        self.pen_var.set(self.pixels[y * TITLE_PIXEL_WIDTH + x])

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(bytes(self.title_data))
        self.title_data = bytearray(self.undo_stack.pop())
        self.pixels = decode_title_pixels(self.title_data)
        self.dirty = True
        self._refresh_all_pixels()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(bytes(self.title_data))
        self.title_data = bytearray(self.redo_stack.pop())
        self.pixels = decode_title_pixels(self.title_data)
        self.dirty = True
        self._refresh_all_pixels()

    def _rebuild_canvas(self) -> None:
        scale = self.zoom_var.get()
        width = TITLE_PIXEL_WIDTH * scale
        height = TITLE_PIXEL_HEIGHT * scale
        self.canvas.configure(width=width, height=height, scrollregion=(0, 0, width, height))
        self.canvas.delete("all")
        self.pixel_items = []
        for y in range(TITLE_PIXEL_HEIGHT):
            row_start = y * TITLE_PIXEL_WIDTH
            for x in range(TITLE_PIXEL_WIDTH):
                color = DISPLAY_COLORS[self.pixels[row_start + x]]
                item = self.canvas.create_rectangle(
                    x * scale,
                    y * scale,
                    (x + 1) * scale,
                    (y + 1) * scale,
                    fill=color,
                    outline="",
                    tags=("pixel",),
                )
                self.pixel_items.append(item)
        for tile_x in range(TITLE_TILE_COLUMNS + 1):
            coordinate = tile_x * 8 * scale
            self.canvas.create_line(coordinate, 0, coordinate, height, fill="#CC7722")
        tile_rows = TITLE_PIXEL_HEIGHT // 8
        for tile_y in range(tile_rows + 1):
            coordinate = tile_y * 8 * scale
            self.canvas.create_line(0, coordinate, width, coordinate, fill="#CC7722")

    def _refresh_all_pixels(self) -> None:
        if not self.pixel_items:
            return
        for index, value in enumerate(self.pixels):
            self.canvas.itemconfigure(self.pixel_items[index], fill=DISPLAY_COLORS[value])

    def _update_pointer_info(self, event: tk.Event) -> None:
        point = self._event_pixel(event)
        if point is None or self.layout is None:
            self.pointer_info_var.set("")
            return
        x, y = point
        tile_x, pixel_x = divmod(x, 8)
        tile_y, pixel_y = divmod(y, 8)
        tile_index = tile_y * TITLE_TILE_COLUMNS + tile_x
        plane_suffix = f"+{pixel_y:X}/+{8 + pixel_y:X}"
        self.pointer_info_var.set(
            f"像素 ({x},{y})  |  图块 ${tile_index:02X}  |  图块起点 "
            f"0x{self.layout.title_active_offset + tile_index * 16:X}  |  位平面 {plane_suffix}"
        )

    def import_png(self) -> None:
        if self.source_path is None:
            messagebox.showinfo("未打开 ROM", "请先打开 ROM。", parent=self.root)
            return
        selected = filedialog.askopenfilename(title="导入 PNG", filetypes=PNG_FILE_TYPES)
        if not selected:
            return
        try:
            image = tk.PhotoImage(file=selected)
            if image.width() != TITLE_PIXEL_WIDTH or image.height() != TITLE_PIXEL_HEIGHT:
                raise ValueError(
                    f"PNG 必须是 {TITLE_PIXEL_WIDTH}×{TITLE_PIXEL_HEIGHT} 像素，"
                    f"当前是 {image.width()}×{image.height()}。"
                )
            rgb_pixels: list[tuple[int, int, int]] = []
            for y in range(TITLE_PIXEL_HEIGHT):
                for x in range(TITLE_PIXEL_WIDTH):
                    raw = image.get(x, y)
                    if isinstance(raw, tuple):
                        rgb = tuple(int(component) for component in raw[:3])
                    else:
                        red, green, blue = self.root.winfo_rgb(str(raw))
                        rgb = (red // 257, green // 257, blue // 257)
                    rgb_pixels.append(rgb)  # type: ignore[arg-type]
            unique = sorted(
                set(rgb_pixels), key=lambda rgb: 299 * rgb[0] + 587 * rgb[1] + 114 * rgb[2]
            )
            if len(unique) <= 4:
                mapping = {color: index for index, color in enumerate(unique)}
                new_pixels = [mapping[color] for color in rgb_pixels]
            else:
                new_pixels = []
                for red, green, blue in rgb_pixels:
                    luminance = (299 * red + 587 * green + 114 * blue) // 1000
                    new_pixels.append(min(3, (luminance * 4) // 256))
            self.undo_stack.append(bytes(self.title_data))
            self.redo_stack.clear()
            self.pixels = new_pixels
            self.title_data = bytearray(encode_title_pixels(self.pixels))
            self.dirty = True
            self._refresh_all_pixels()
            self.status_var.set(f"已导入 PNG：{selected}")
        except Exception as error:
            messagebox.showerror("导入失败", str(error), parent=self.root)

    def export_png(self) -> None:
        if self.source_path is None:
            messagebox.showinfo("未打开 ROM", "请先打开 ROM。", parent=self.root)
            return
        selected = filedialog.asksaveasfilename(
            title="导出 PNG",
            defaultextension=".png",
            filetypes=PNG_FILE_TYPES,
            initialfile=f"{self.source_path.stem}_标题图块.png",
            confirmoverwrite=True,
        )
        if not selected:
            return
        try:
            image = tk.PhotoImage(width=TITLE_PIXEL_WIDTH, height=TITLE_PIXEL_HEIGHT)
            for y in range(TITLE_PIXEL_HEIGHT):
                row = self.pixels[y * TITLE_PIXEL_WIDTH : (y + 1) * TITLE_PIXEL_WIDTH]
                color_row = " ".join(DISPLAY_COLORS[value] for value in row)
                image.put("{" + color_row + "}", to=(0, y))
            image.write(selected, format="png")
            self.status_var.set(f"已导出 PNG：{selected}")
        except Exception as error:
            messagebox.showerror("导出失败", str(error), parent=self.root)

    def show_safety_help(self) -> None:
        messagebox.showinfo(
            "安全保存",
            "编辑器根据 iNES Header 计算活动 CHR，不使用 CT2 保存的旧绝对偏移。\n\n"
            "扩容 ROM 另存时，活动 CHR 和旧影子会写入同一份标题数据。\n"
            "源 ROM 不会被覆盖，音乐 Bank、事件数据和其他 CHR 不会改动。",
            parent=self.root,
        )

    def on_close(self) -> None:
        if self._confirm_discard():
            self.root.destroy()


def _run_self_test(arguments: list[str]) -> int:
    """Exercise the frozen GUI and ROM pipeline without showing a window."""

    if len(arguments) != 3:
        return 2
    source_path = Path(arguments[0])
    output_path = Path(arguments[1])
    report_path = Path(arguments[2])
    report: dict[str, object] = {
        "source": str(source_path),
        "output": str(output_path),
        "status": "failed",
    }
    try:
        root = tk.Tk()
        root.withdraw()
        app = TitleEditorApp(root)
        root.update_idletasks()
        gui_pixel_items = len(app.pixel_items)
        root.destroy()

        source_data, source_layout, source_copies = read_rom(source_path)
        selected_title = (
            source_copies.shadow
            if source_layout.expanded and source_copies.mismatch_count
            else source_copies.active
        )
        _, output_sha256 = save_title_copy(
            source_path, output_path, selected_title, mirror_shadow=True
        )
        output_data = output_path.read_bytes()
        output_layout = parse_nes_layout(output_data)
        output_copies = get_title_copies(output_data, output_layout)

        allowed = set(
            range(
                output_layout.title_active_offset,
                output_layout.title_active_offset + TITLE_BLOCK_SIZE,
            )
        )
        allowed.update(
            range(
                output_layout.title_shadow_offset,
                output_layout.title_shadow_offset + TITLE_BLOCK_SIZE,
            )
        )
        changed = [
            index
            for index, (old, new) in enumerate(zip(source_data, output_data))
            if old != new
        ]
        outside_title = sum(index not in allowed for index in changed)
        if output_copies.mismatch_count != 0 or outside_title != 0:
            raise RuntimeError(
                "Self-test output changed data outside the title copies or left them mismatched."
            )

        report.update(
            {
                "status": "passed",
                "mapper": output_layout.mapper,
                "prgSize": output_layout.prg_size,
                "chrSize": output_layout.chr_size,
                "activeTitleOffset": f"0x{output_layout.title_active_offset:X}",
                "shadowTitleOffset": f"0x{output_layout.title_shadow_offset:X}",
                "sourceCopyMismatchBytes": source_copies.mismatch_count,
                "outputCopyMismatchBytes": output_copies.mismatch_count,
                "changedBytes": len(changed),
                "outsideTitleChangedBytes": outside_title,
                "guiPixelItems": gui_pixel_items,
                "sourceSha256": sha256_bytes(source_data),
                "outputSha256": output_sha256,
            }
        )
        return_code = 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        return_code = 1
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return return_code


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        raise SystemExit(_run_self_test(sys.argv[2:]))
    root = tk.Tk()
    app = TitleEditorApp(root)
    if len(sys.argv) > 1:
        root.after(50, lambda: app.open_rom(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()
