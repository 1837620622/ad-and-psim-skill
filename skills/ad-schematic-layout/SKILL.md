---
name: ad-schematic-layout
description: Create, edit and lay out editable Altium Designer schematics (SchDoc/PrjPcb) from natural language on any OS, pass a deterministic layout check, render previews, then compile, compare pin-level nets, export and screenshot natively on Windows. Use for AD schematic modeling, reproducing a reference drawing, tidying an existing sheet and delivering clean project folders. 用自然语言在任何系统上创建、修改和排版可编辑的 Altium Designer 原理图，经排版预检后在 Windows 上原生编译、核对网络、出图和截图，并整理交付。
license: Proprietary commercial authorization required. See LICENSE.
metadata:
  compatibility: Python 3.10+ on Windows, macOS or Linux for planning, creation, editing, handoff, reception and comparison. Native compilation/export needs Windows with Altium Designer; receiving the native PNG needs no vendor software on Mac/Linux.
---

# AD 原理图建模与排版

把用户的电路要求做成可编辑、能在 AD 里直接打开的原理图，排版达到正式工程图的水平。

## 能在哪做什么

| 操作 | 任何系统 | 需要 Windows + AD |
| --- | --- | --- |
| 写计划、排版预检、草图预览 | ✓ | |
| 生成 SchDoc + PrjPcb（各系统字节一致） | ✓ | |
| 导入现有 SchDoc、按操作清单修改、仿原生渲染 | ✓ | |
| 离线预测编译 warning、网表和图面（`preflight`） | ✓ | |
| 原生编译、逐引脚网表、原生出图、窗口截图 | | ✓ |
| 整理交付目录 | ✓ | |
| 准备交给 Windows 的任务、接收原生 PNG 与结果、比较文件 | ✓ | |

在 macOS/Linux 生成的 SchDoc 发到 Windows 用 AD 打开，内容与在 Windows 上生成的完全相同；交付前仍要在 Windows 上做一次原生编译和出图。

## 工作流程

1. **定范围。** 读要求和原工程，列出必须有、可选、不做的内容。要求"一张总图""一个完整芯片符号"就照做，不自行加页、加模块。
2. **读排版规则。** 每次排图前读 [排版硬规则](references/drafting-rules.md)，按其中的栅格、字位、间距和比例写计划。有客户参考图时先量参考的比例。
3. **写计划并预检。** 计划格式和全部命令见 [命令与计划格式](references/commands.md)。运行 `check`，修到 0 error（文字重叠是 error）；位号、参数压字压线时用编辑操作 `place_text` 自动摆放；每条 warning 要么改掉，要么在交付说明里写理由。看一眼草图预览。
4. **离线预测。** `preflight` 给出仿原生预览、预计的编译 warning（缺封装数）和网表是否与 pin_map 一致；`ready_for_windows` 为 true 再往下。
5. **生成文件。** `create` 写出 SchDoc 与 PrjPcb；预检有 error 时它会拒绝写出。
6. **改已有图。** `import` 把现有 SchDoc 转成计划，`edit` 按操作清单修改（移动器件时相连导线自动正交重连），再 `create` 到新目录。带库图形的原生器件不能导入，改用原生脚本，见 [原生操作与电气检查](references/native-and-electrical.md)。
7. **原生确认（Windows）。** `verify` 编译并比较逐引脚网表；`export` 原生出图，结果里的 `text_review` 必须通过（无文字重叠、越界、压线），再逐区看图。
8. **交付。** `deliver --clean` 生成客户目录：只放工程和原生图纸，不放 JSON、脚本和日志，不打压缩包，并清理缓存。见 [核验与交付](references/verification-and-delivery.md)。

在 Mac/Linux 上工作时，用 `handoff` 准备完整任务目录，传到 Windows 双击 `run.bat`，再用 `receive` 校验接收。PNG 渲染默认仿 Windows 原生出图（RC 示例与原生导出尺寸相同，线条和文字像素 97.8% 在 1 像素内对齐），用来在没有 AD 时看效果；对外和最终确认仍以接收回来的原生 PNG 为准，接收器不重绘它。详见 [交接与结果一致性](references/handoff.md)。

## 逐步操作（照着做）

每条命令都在本技能目录下运行，打印 JSON。只按 JSON 里的字段判断成败，不凭感觉。

1. **看环境。** `python scripts/native_ad.py env`，看本机有没有 AD、仿原生预览能不能用。没有 AD 也能生成 SchDoc，只是编译和原生出图要到 Windows 上做。
2. **从示例开始写计划。** 把 [assets/rc-filter-plan.json](assets/rc-filter-plan.json) 复制成 `work/plan.json` 再改，不要从空白写起。`units` 固定 `"10mil"`，坐标向右、向上；R/C/L/Y 写 `ref`、`value`、`at`（中心）和 `vertical`；芯片和接插件写 `body` 与 `pins`（`number`、`name`、`at` 在框边上、`direction`）。`pin_map` 写每个引脚应属的网络，预检靠它核对连接。
3. **坐标规则。** 引脚热端、导线端点、标号和电源端口锚点都在 10 的倍数上；导线点可以直接写 `"R1.1"` 这样的引脚名，斜线会自动补成直角折线；局部外围直接连线，跨区才用网络标号；电源符号朝上、地朝下，就近放在引脚处。
4. **预检到 0 error。** `python scripts/native_ad.py check work/plan.json --preview draft.png`。看 `summary.errors`：
   - 每条 finding 都有 `code`、`message`、`hint`，按 `hint` 改计划。
   - 文字问题（`TEXT_OVERLAP`、`TEXT_ON_PART`、`TEXT_ON_GRAPHICS`、`TEXT_NEAR_LINE`、`OUTSIDE_BORDER`）不要手算坐标，写操作清单 `[{"op": "place_text", "all": true}]`，运行 `edit work/plan.json ops.json work/plan2.json`，再对新文件 `check`。
   - `PART_OVERLAP` 用 `move` 拉开器件；`PIN_OFF_GRID` 把坐标改成 10 的倍数；`TOPOLOGY_MISMATCH` 说明导线和 `pin_map` 对不上，按 finding 里的引脚改导线；内容太散或太挤用 `fit_canvas`。
   - 重复到 `errors` 为 0。warning 能改就改，留下的在交付说明里写理由。
5. **离线预测。** `python scripts/native_ad.py preflight work/plan2.json preflight/`。`ready_for_windows` 为 true 才继续；为 false 时按 `blocking` 逐条修。`expected_warnings` 是预计的编译 warning（例如缺封装），要在交付说明里写明。
6. **生成工程。** `python scripts/native_ad.py create work/plan2.json out/`，得到 `.SchDoc` 和 `.PrjPcb`。任何系统生成的文件都相同，拷到 Windows 双击 `.PrjPcb` 就能用 AD 打开。不要手写或改动 SchDoc 二进制。
7. **Windows 原生确认。** 在装有 AD 的 Windows 上运行 `verify`（编译并比较网表）和 `export`（`text_review` 必须通过）。在 Mac/Linux 上就用 `handoff work/plan2.json job/`，把 `job/` 拷到 Windows 双击 `run.bat`，拿回 `native-results/` 后运行 `receive`。
8. **交付。** 在 Windows 上直接做的，把原生图导出到工程目录里（`export out/X.SchDoc out/drawing/`），再运行 `python scripts/native_ad.py deliver out/ delivery/ --name 项目名 --clean`；用 `handoff` 的，`receive` 得到的 `final/` 里已有工程和原生图，运行 `deliver final/ delivery/ --name 项目名 --clean`。客户目录只能有 PrjPcb、SchDoc、库文件和原生图纸；看结果里的 `delivered`，出现 `.json`、`.py`、`.pas`、`.log` 就是出错了。不要另外拷文件进客户目录。

常见错误：

| 现象 | 处理 |
| --- | --- |
| `create` 拒绝写出 | 预检还有 error，回到第 4 步 |
| Windows 上找不到 AD | 设置 `AD_EXE` 为 `X2.EXE` 的完整路径（带不带引号都行），再运行 |
| `run.bat` 提示缺 Python 或 Pillow | 按窗口里给的命令安装 Python 3.11+ 和 Pillow 后重跑 |
| 运放、MOSFET 都成了方框 | 基础生成器只画矩形器件和 R/C/L/Y，这类器件用原生库，见 [原生操作与电气检查](references/native-and-electrical.md) |

## 命令速查

所有命令在本技能目录下运行，输出 JSON：

```text
python scripts/native_ad.py env                                   # 本机能做什么
python scripts/native_ad.py check plan.json --preview draft.png   # 排版预检 + 草图
python scripts/native_ad.py preflight plan.json preflight/         # 离线预测：仿原生预览、编译 warning
python scripts/native_ad.py create plan.json out/                 # 写出 SchDoc + PrjPcb
python scripts/native_ad.py import current.SchDoc plan.json       # 现有图纸转计划
python scripts/native_ad.py edit plan.json ops.json new-plan.json # 按操作清单修改
python scripts/native_ad.py render out/X.SchDoc view.png          # 仿原生渲染（无需 AD）
python scripts/native_ad.py screenshot out/X.SchDoc shot.png      # 有 AD 截窗口，否则渲染
python scripts/native_ad.py open out/X.PrjPcb                     # Windows：用 AD 打开（Mac/Linux 生成的文件可直接打开）
python scripts/native_ad.py verify out/X.PrjPcb verify/ --expected out/expected.json
python scripts/native_ad.py export out/X.SchDoc out/drawing/       # 原生出图放进工程目录，交付时一起带上
python scripts/native_ad.py deliver out/ delivery/ --name X --clean  # 客户目录只放工程和图纸
python scripts/native_ad.py handoff plan.json job/
python scripts/native_ad.py receive job/ returned-results/ final/
python scripts/native_ad.py compare reference.SchDoc final/X.SchDoc
```

`scripts/mcp_server.py` 把这些命令作为 MCP 工具提供，见 [命令与计划格式](references/commands.md#mcp)。

## 底线

- 连接以原生网表为准：标号和端口的锚点必须在导线或热端上，文字挨着不算连接。
- 图上的位号和参数用关联属性，改值后重新生成，不用静态文字盖住旧值。
- 便携渲染和草图只用于调试，对外的图用 AD 原生出图或真实窗口截图，并说明来源。
- 编译 0 error 不等于 0 warning，也不等于能直接制板；结论写清楚验证到哪一步。
- 客户目录只放工程和正式图纸。计划和报告 JSON、Python 和 DelphiScript 脚本、批处理、日志都是过程文件，一律不交付；交付用 `deliver`，不要手工拷贝。

## 参考资料

| 需要时读 | 文件 |
| --- | --- |
| 排版数字、去 AI 味检查单、三道闸门 | [drafting-rules.md](references/drafting-rules.md) |
| 全部命令、计划格式、编辑操作、MCP | [commands.md](references/commands.md) |
| 原生 API、改库改连接、完整芯片检查 | [native-and-electrical.md](references/native-and-electrical.md) |
| 网表比较、出图审查、交付目录 | [verification-and-delivery.md](references/verification-and-delivery.md) |
| 官方参考图来源和已经踩过的坑 | [sources-and-lessons.md](references/sources-and-lessons.md) |
| Mac/Linux 交接、原生预览、哈希与波形比较 | [handoff.md](references/handoff.md) |

本技能为专有商业授权，见 [LICENSE](LICENSE)；微信 1837620622。
