# DC 音乐替换项目

本仓库用于 NES ROM 的音乐替换、扩容、探测与验证。详细的长期维护规则见 [`AGENTS.md`](AGENTS.md)。

## 目录

- `src/`：正式源码和核心实现。
- `assets/`：参与构建并需要版本控制的音乐及其他素材。
- `tools/`：构建、转换、探测和校验工具。
- `inputs/`：本地只读输入，默认不提交。
- `build/`：可重建的中间产物，禁止提交。
- `dist/`：通过验证的最终交付物。
- `evidence/`：精选的验证证据。
- `docs/`：设计和研究文档。
- `tests/`：自动化测试与夹具。

当前可交付 ROM 位于 `dist/roms/`，文件大小和哈希见 [`dist/MANIFEST.md`](dist/MANIFEST.md)。

两份 15 曲扩容未绑定版已经完成。布局、命令表、FCEUX 兼容原理和修改器使用顺序见
[`docs/扩容15曲实现与命令表.md`](docs/扩容15曲实现与命令表.md)，运行时证据见
[`evidence/2026-09-17-扩容15曲/验证记录.md`](evidence/2026-09-17-扩容15曲/验证记录.md)。

扩容 ROM 的标题图块请使用免 Python 的 [`dist/tools/扩容ROM标题编辑器.exe`](dist/tools/扩容ROM标题编辑器.exe)，它会根据 Header 定位活动 CHR，并可恢复 CT2 写入旧影子的修改。

机体、碎片和拼图等旧修改器功能优先使用 [`dist/tools/新DC扩容专用修改器/新DC扩容专用修改器.exe`](dist/tools/新DC扩容专用修改器/新DC扩容专用修改器.exe)。新入口会隐藏并自动跳过贴吧/QQ 群启动页；旧核心初始化较慢时会循环重试进入，失败时不会遗留隐藏后台进程。工作核心被改写后会从已验证压缩备份自动恢复；保存后还会根据前后差分自动协调旧 CHR 影子与活动 CHR 的单边写入。

只有继续使用未打补丁、只会写旧 CHR 偏移的原修改器时，才在保存后使用免 Python 的 [`dist/tools/扩容ROM全CHR同步工具.exe`](dist/tools/扩容ROM全CHR同步工具.exe) 将完整 256 KiB 旧影子同步到活动 CHR。
