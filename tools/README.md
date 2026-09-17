# 工具

构建、转换、探测、提取和校验脚本放在此目录。工具应使用相对仓库根目录的路径，并在文件头或相邻文档中说明输入、输出和运行方式。

`build_refined15_roms.py` 从两份 512 KiB PRG 基线一步生成 1 MiB PRG 的 15 曲未绑定版。它需要 Python `capstone` 与 `asm6_fixed.exe`，并强制检查旧文件体逐字节不变。完整用法见 `docs/扩容15曲实现与命令表.md`。

`启动扩容标题编辑器.cmd` 启动可视化标题 CHR 编辑器，可直接读写扩容 ROM 的活动 CHR，并可恢复 CT2 留在旧偏移的修改。

`package_expanded_title_editor.py` 将编辑器源码、启动器和说明打包到 `dist/tools/`，同时生成便于分发的 ZIP。

`启动扩容ROM全CHR同步工具.cmd` 启动旧 CHR 影子→活动 CHR 的 256 KiB 整区同步工具；`package_expanded_chr_sync.py` 生成其便携目录和 ZIP。

`build_expanded_chr_sync_exe.py` 使用 Windows 自带的 .NET Framework 4.x C# 编译器生成不依赖 Python 的单文件 WinForms EXE。

`patch_legacy_modifier_expanded_chr.py` 对已审计的旧 SRW2 修改器打扩容 CHR 定位补丁，将 14 处 `$080010` 常量修改为活动 CHR `$100010`；只接受文档锁定的输入哈希。

`launch_legacy_modifier_expanded_chr_candidate.cmd` 在保留 `inputs/` 原件的前提下重建补丁 EXE，供维护和复核。已完成运行验收的唯一用户版位于 `dist/tools/新DC扩容专用修改器/`，只能用于 1 MiB PRG 扩容 ROM。

`build_modifier_skip_launcher.py` 编译新DC扩容专用修改器的外层入口，将已审计的 CHR 补丁核心及其本地 INI/DAT 配置镜像放入“内部文件”，并生成不显示旧启动页、保存后自动协调双 CHR 副本的便携目录与 ZIP。

`build_expanded_title_editor_exe.py` 使用固定版本 PyInstaller 生成无控制台、单文件 Windows EXE；运行生成的 EXE 不需要目标电脑安装 Python。
构建依赖锁定在 `title_editor_packaging_requirements.txt`。
