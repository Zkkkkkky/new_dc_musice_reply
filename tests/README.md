# 测试

自动化测试、测试夹具和最小复现放在此目录。测试生成物应写入 `build/` 或系统临时目录。

运行：

```powershell
python -m unittest discover -s tests -v
```

当前测试锁定两份源 ROM 与交付 ROM 的 SHA-256，并验证旧文件体、扩容布局、FCEUX 清锁代码和 15 曲命令表。

`test_expanded_title_editor.py` 验证扩容/原版 CHR 偏移计算、NES 2bpp 往返编码、影子同步和“禁止覆盖源 ROM”规则。

`test_expanded_chr_sync.py` 验证完整 256 KiB 旧 CHR 影子到活动 CHR 的单向同步、区域边界与源 ROM 保护。

`test_legacy_modifier_expanded_chr.py` 验证旧修改器 CHR 常量补丁只改动每个 `imm32` 的必要字节，并对额外或错位常量拒绝输出。

`test_modifier_skip_launcher.py` 验证新入口的窗口匹配、三秒初始化延时、内部核心哈希锁定/自动恢复、便携 ZIP 边界，以及旧影子/活动 CHR 两种单边写入的差分同步。

`test_expanded_dc_cipher.py` 验证原版/1 MiB PRG 扩容布局、加密态判定、Bank `$3F/$7F` 同步、仅 5/6 字节变更、逐字节往返和「禁止覆盖源 ROM」。

`src/lua/dc_cipher_mesen_boot_smoke.lua` 与 `src/lua/dc_cipher_fceux_boot_smoke.lua` 分别验证加密/解密态扩容 ROM 能在 MesenCE 和 FCEUX 冷启动并持续执行。
