# 三目童子五曲替换 JUST COMMUNICATION 接入

## 交付结果

以用户提供的两份 Mapper 194 扩容 ROM 为只读基线，删除精修曲 `JUST COMMUNICATION - 高达EW精修`，并加入五首《三目童子》曲目：

- `dist/roms/新DC上_三目童子5曲_替换JUST.nes`
- `dist/roms/新DC下_三目童子5曲_替换JUST.nes`

原始文件 `D:/LLM/outputs/新DC上.nes` 和 `新DC下.nes` 没有被覆盖。

## 命令与 Bank

| 逻辑编号 | 命令 | 数据 Bank | 驱动 Bank | 曲目 |
| ---: | ---: | ---: | ---: | --- |
| `$1D` | `$A0` | `$6F` | `$74` | Stage 5-2（替换 JUST） |
| `$24` | `$A7` | `$79` | `$74` | Stage 5-3 |
| `$25` | `$A8` | `$7A` | `$7B` | Boss Fight |
| `$26` | `$A9` | `$7C` | `$74` | Introduction |
| `$27` | `$AA` | `$7D` | `$74` | Ending (Epilogue) |

Boss Fight 的 NSF 有第三个 4 KiB 数据页，因此 `$7B` 的低 4 KiB 保存额外数据，高 4 KiB 保存与 `$74` 相同的重定位公共驱动及包装器。

`$9D-$9F` 继续作为安全空命令。下版 `$A6/$78` 的 `LAST IMPRESSION` 保持不变；上版 `$78` 保持空白。

## 曲目数量与余量

- 上版：原版 20 首＋精修 19 首，共 39 首；Bank `$78` 仍空，可再放一首普通尺寸精修曲。
- 下版：原版 20 首＋精修 20 首，共 40 首；`$78-$7D` 已全部使用。

本次没有猜测角色、地图或剧情绑定。若原 ROM 已有 `$A0` 绑定，它会自然从 JUST 改为 Stage 5-2；`$A7-$AA` 目前仅保证命令可触发。

## 保存范围

构建器 `tools/add_mitsume5_replace_just_to_expanded_roms.py` 锁定两份输入哈希，并仅允许修改以下扩展槽：

- `$64` 的双引擎桥接器；
- `$6F` 的原 JUST 数据；
- `$74/$75` 包装器的数据映射入口和 `$BF00` 扩展槽；
- `$76` 调度器；
- `$79-$7D` 新曲数据及 Boss Fight 驱动 Bank。

原始 PRG `$00-$3F`、CHR 影子、活动 CHR、Bank `$60-$63`、其余已有精修曲、`It's Not Anime` 的第三页、音效 Bank `$77`、Bank `$78` 和固定 Bank `$7E/$7F` 均逐字节保留。

## 验证

- Mesen 0.9.9：上下版五首新曲的真实数据/驱动 Bank、INIT/PLAY、APU 写入、返回原引擎、旧 BSS 和 DMC 路径检查全部通过。
- Mesen 0.9.9：下版原有 `$A6/$78` `LAST IMPRESSION` 单独复测通过。
- FCEUX 2.6.6：上版 19 首精修曲矩阵 `pass=true`，下版 20 首精修曲矩阵 `pass=true`。
- 上版输入原有两处 `$4800` 写保持不变；下版原有 `$5000=$27` 清锁保持不变。

完整证据见 `evidence/2026-09-20-三目童子五曲替换JUST/`。
