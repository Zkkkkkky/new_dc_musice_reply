# 工具

构建、转换、探测、提取和校验脚本放在此目录。工具应使用相对仓库根目录的路径，并在文件头或相邻文档中说明输入、输出和运行方式。

`build_refined15_roms.py` 从两份 512 KiB PRG 基线一步生成 1 MiB PRG 的 15 曲未绑定版。它需要 Python `capstone` 与 `asm6_fixed.exe`，并强制检查旧文件体逐字节不变。完整用法见 `docs/扩容15曲实现与命令表.md`。

`add_last_impression_to_expanded_rom.py` 在已验证的 15 曲扩容 ROM 上追加 `LAST IMPRESSION`：使用命令 `$A6`、逻辑编号 `$23`和数据 Bank `$78`，同时恢复 FCEUX `$5000` 清锁。它拒绝覆盖非空 `$78`，且永不原地覆盖输入。

`convert_mitsume_to_refined_driver.py` 将五个三目童子原生 NSF 的实际 APU 演奏轨迹转换为可编辑 FamiStudio 工程，精确探测循环，并绑定为 ROM 精修曲的 `$F000/$F100/$F160` 公共驱动。需要 FamiStudio 4.5.3 和 Python `py65`。

`codex-skills/nsf-refined-common-driver/` 将上述转换能力封装为可安装的 Codex skill。它带有通用单曲 2A03 NSF 入口、三目童子五曲专用 profile、清单式 DPCM/驱动配置覆盖，以及循环和逐帧听感强制校验；不包含任何 NSF 或 ROM 原件。

`convert_ninja_gaiden_to_refined_driver.py` 将 `$FC00/$C040/$8000` 的《鲜烈之龙（4-2）》转换为同一精修公共驱动；它支持非 4 KiB 对齐 NSF Bank 映射，并校验 DPCM 采样字节与触发时刻。需要 FamiStudio 4.5.3 和 Python `py65`。

`add_mitsume5_replace_just_to_expanded_roms.py` 锁定用户提供的两份扩容 ROM，以 Stage 5-2 替换 `$A0/$6F` 的 JUST，并将其余四首映射到 `$A7-$AA`；Boss Fight 使用 `$7A` 数据 Bank 和 `$7B` 第三页驱动 Bank。工具拒绝覆盖输入并执行允许修改范围门禁。

`启动扩容标题编辑器.cmd` 启动可视化标题 CHR 编辑器，可直接读写扩容 ROM 的活动 CHR，并可恢复 CT2 留在旧偏移的修改。

`package_expanded_title_editor.py` 将编辑器源码、启动器和说明打包到 `dist/tools/`，同时生成便于分发的 ZIP。

`启动扩容ROM全CHR同步工具.cmd` 启动旧 CHR 影子→活动 CHR 的 256 KiB 整区同步工具；`package_expanded_chr_sync.py` 生成其便携目录和 ZIP。

`build_expanded_chr_sync_exe.py` 使用 Windows 自带的 .NET Framework 4.x C# 编译器生成不依赖 Python 的单文件 WinForms EXE。

`patch_legacy_modifier_expanded_chr.py` 对已审计的旧 SRW2 修改器打扩容 CHR 定位补丁，将 14 处 `$080010` 常量修改为活动 CHR `$100010`；只接受文档锁定的输入哈希。

`launch_legacy_modifier_expanded_chr_candidate.cmd` 在保留 `inputs/` 原件的前提下重建补丁 EXE，供维护和复核。已完成运行验收的唯一用户版位于 `dist/tools/新DC扩容专用修改器/`，只能用于 1 MiB PRG 扩容 ROM。

`build_modifier_skip_launcher.py` 编译新DC扩容专用修改器的外层入口，打包已审计 CHR 补丁核心、确定性 gzip 恢复源和核心旁 INI/DAT 配置镜像，并生成可重试跳过旧启动页、失败不遗留隐藏核心、保存后自动协调双 CHR 副本的便携目录与 ZIP。

`build_expanded_title_editor_exe.py` 使用固定版本 PyInstaller 生成无控制台、单文件 Windows EXE；运行生成的 EXE 不需要目标电脑安装 Python。
构建依赖锁定在 `title_editor_packaging_requirements.txt`。

`启动扩容ROM加密解密工具.cmd` 启动可审计源码版；`build_expanded_dc_cipher_exe.py` 生成免 Python 的单文件 Windows EXE。该工具严格校验 Mapper 194 布局，扩容版同步 `$07F4C8` 与 `$0FF4C8`，并禁止覆盖源 ROM。
打包依赖锁定在 `dc_cipher_packaging_requirements.txt`。
