# 源码

正式、可维护、参与生成最终产物的源码放在此目录。按语言或模块继续划分子目录，禁止提交生成文件。

- `asm/`：Mapper 194 扩容桥接、Bank 跳板、重定位驱动包装器和原版音效数据。
- `lua/`：Mesen 0.9.9 与 FCEUX 2.6.6 的 15 曲运行时回归脚本。
- `title_editor/`：根据 iNES Header 定位活动 CHR、并同步扩容影子的标题图块编辑器。
- `chr_sync/`：将旧修改器写入的完整 256 KiB CHR 影子安全同步到扩容 ROM 活动 CHR；包含 Python/Tkinter 可审计源码与免 Python 的 C# WinForms 实现。
- `modifier_launcher/`：扩容专用旧修改器的可审计 C# 入口；校验内部核心、跳过旧启动页，并在保存后差分协调旧 CHR 影子与活动 CHR。
