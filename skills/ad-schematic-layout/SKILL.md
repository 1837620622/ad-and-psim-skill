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
| 导入现有 SchDoc、按操作清单修改、便携渲染 | ✓ | |
| 原生编译、逐引脚网表、原生出图、窗口截图 | | ✓ |
| 整理交付目录 | ✓ | |
| 准备交给 Windows 的任务、接收原生 PNG 与结果、比较文件 | ✓ | |

在 macOS/Linux 生成的 SchDoc 发到 Windows 用 AD 打开，内容与在 Windows 上生成的完全相同；交付前仍要在 Windows 上做一次原生编译和出图。

## 工作流程

1. **定范围。** 读要求和原工程，列出必须有、可选、不做的内容。要求"一张总图""一个完整芯片符号"就照做，不自行加页、加模块。
2. **读排版规则。** 每次排图前读 [排版硬规则](references/drafting-rules.md)，按其中的栅格、字位、间距和比例写计划。有客户参考图时先量参考的比例。
3. **写计划并预检。** 计划格式和全部命令见 [命令与计划格式](references/commands.md)。运行 `check`，修到 0 error；每条 warning 要么改掉，要么在交付说明里写理由。看一眼草图预览。
4. **生成文件。** `create` 写出 SchDoc 与 PrjPcb；预检有 error 时它会拒绝写出。
5. **改已有图。** `import` 把现有 SchDoc 转成计划，`edit` 按操作清单修改（移动器件时相连导线自动正交重连），再 `create` 到新目录。带库图形的原生器件不能导入，改用原生脚本，见 [原生操作与电气检查](references/native-and-electrical.md)。
6. **原生确认（Windows）。** `verify` 编译并比较逐引脚网表；`export` 原生出图，结果里的 `text_review` 必须通过（无文字重叠、越界、压线），再逐区看图。
7. **交付。** `deliver` 生成两个目录：给客户的只有工程和图纸，过程文件放归档目录，不打压缩包。见 [核验与交付](references/verification-and-delivery.md)。

在 Mac/Linux 上工作时，用 `handoff` 准备完整任务目录，传到 Windows 双击 `run.bat`，再用 `receive` 校验接收。要确认与实际软件的图面一致，直接查看接收的原生 PNG；接收器不重绘它。离线便携渲染仍是近似预览，不能声称任意器件和字体逐像素一致。详见 [交接与结果一致性](references/handoff.md)。

## 命令速查

所有命令在本技能目录下运行，输出 JSON：

```text
python scripts/native_ad.py env                                   # 本机能做什么
python scripts/native_ad.py check plan.json --preview draft.png   # 排版预检 + 草图
python scripts/native_ad.py create plan.json out/                 # 写出 SchDoc + PrjPcb
python scripts/native_ad.py import current.SchDoc plan.json       # 现有图纸转计划
python scripts/native_ad.py edit plan.json ops.json new-plan.json # 按操作清单修改
python scripts/native_ad.py render out/X.SchDoc view.png          # 便携渲染（无需 AD）
python scripts/native_ad.py screenshot out/X.SchDoc shot.png      # 有 AD 截窗口，否则渲染
python scripts/native_ad.py verify out/X.PrjPcb verify/ --expected out/expected.json
python scripts/native_ad.py export out/X.SchDoc drawing/
python scripts/native_ad.py deliver out/ delivery/ --name X
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
