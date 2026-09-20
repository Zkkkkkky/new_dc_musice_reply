# LAST IMPRESSION 扩容 16 曲接入

## 交付物

`dist/roms/新DC下_扩容16曲_LAST IMPRESSION_未绑定.nes`

该 ROM 以用户提供的扩容 `新DC下.nes` 为只读基线，保留原有 15 曲、游戏数据和 CHR，新增一首未绑定的 `LAST IMPRESSION`。

## 命令与 Bank

| 扩展编号 | 实际命令 | 数据 Bank | 驱动 |
| ---: | ---: | ---: | --- |
| `$23` | `$A6` | `$78` | Bank `$74` 的现有重定位公共驱动 |

Bank `$78` 从保留区正式分配为第 16 首曲的 8 KiB 数据 Bank。Bank `$79-$7D` 仍保留且全零，`$61-$63` 的旧测试区也继续保持全零。

## 运行时变更

- Bank `$64` 桥接器将新命令上限从 `$A5` 扩展到 `$A6`。
- Bank `$74/$75` 包装器将 `$A6` 映射到 Bank `$78`。
- Bank `$60` 保留目标 ROM 的原版音频数据，仅更新入口跳板和音频交还槽，恢复 FCEUX 需要的两处 `$5000=$27` 清锁。
- Bank `$65-$73` 原 15 曲数据、Bank `$74/$75` 公共驱动主体、Bank `$76` 调度器和 Bank `$77` 音效数据均保持不变。

## 重建

```powershell
python tools\add_last_impression_to_expanded_rom.py `
  <已有扩容15曲ROM> `
  --output <新的16曲ROM> `
  --asm6 <FamiStudio-4.5.3\Tools\asm6_fixed.exe>
```

工具严格验证旧桥接器、包装器、调度器、NSF 公共驱动和空 Bank，拒绝覆盖非预期数据。

## 绑定状态

本交付仅新增命令 `$A6`，没有修改角色、地图或剧情音乐表。需要实际场景绑定时，应使用 `$A6`。
