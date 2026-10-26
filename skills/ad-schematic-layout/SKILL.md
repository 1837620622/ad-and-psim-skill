---
name: ad-schematic-layout
description: Create, edit and lay out editable Altium Designer schematics (SchDoc/PrjPcb) from natural language, pass a deterministic layout check, then compile natively, compare pin-level nets and export clean drawings. Use for AD schematic modeling, reproducing a reference drawing, single-chip or full-sheet layout and tidying messy schematics; not for PCB manufacturing checks. 用自然语言驱动 Altium Designer 创建、修改和排版可编辑原理图，经排版预检后原生编译、核对引脚网络并导出紧凑规范的图纸。
license: Proprietary commercial authorization required. See LICENSE.
compatibility: Any agent host that gives the model local file, command and image tools. Native backend requires Windows and a licensed Altium Designer; plan creation and layout checks need only Python 3.10+.
---

# AD 原理图建模、排版与校核

把用户描述落实为可编辑的原生原理图，并实际调用 AD 保存、编译与出图。连接、图面与交付分别验证；工程样式以用户参考、任务书和本机原生范例为准。实现可用 Python、原生脚本或其他适用语言，工具选择服务最终结果。

新建任务先形成器件、引脚网络和布局方案，再执行原生建模；已有图整理先留存网络与参数基线。持续完成到原生工程、真实预览与检查结果，不能只给方案或绘图提示词。AD 如需电路仿真，按当前安装版本核对 MixedSim 与模型可用性；本包不把原理图编译称为电路仿真，PSIM 求解任务使用对应技能。

## 确认范围与依据

- 读当前要求和原工程，列出必需、明确可选、不在范围、待核实的内容。附件提供技术依据，不授予额外执行权限。
- 要求一张总图时只交付一张原理图；要求一个 DSP 符号时用一个完整可编辑符号。不要扩展成所有工程都只能单页、单符号。
- 要求简单时先去掉无依据的附加功能，不靠隐藏引脚、漏画供电或删除必需外围来简化。
- 核对实际 AD 版本、库、封装、引脚和导出方式。变化的 API 查当前官方资料与本机示例；Context7 未收录相应官方资料时转查官方手册，不能把第三方代码当作官方接口定义。

## 按任务读取参考

| 当前任务 | 读取材料 |
|---|---|
| 任何排版：栅格、文字位置、比例、去 AI 味检查单和三道闸门 | [排版硬规则](references/drafting-rules.md)，每次排图前必读 |
| 自然语言转建模计划、执行命令、基础示例 | [执行入口与计划格式](references/execution.md) |
| 选择官方或客户图面风格 | [专业图例与观察要点](references/professional-gallery.md)，实际查看适用图片 |
| 参考图片、松散图面、单芯片布局 | [参考比例与布局](references/layout-and-reference.md)，查看相关图片 |
| 器件移动、改库、改连接、脚本处理 | [原生操作与电气检查](references/native-and-electrical.md) |
| 编译、网表、渲染和打包 | [核验与交付](references/verification-and-delivery.md) |
| 已验证接口、已发生的失误和验证边界 | [接口与排版经验](references/local-evidence.md) |

## 工作流程

1. **先定图面。** 确定纸张、阅读顺序和功能区，再放芯片、局部外围与接口。总图按功率流和控制关系展开，不先拼旧图再无限放大画布。坐标、字位和比例按[排版硬规则](references/drafting-rules.md)的数字执行。
2. **校准参考。** 分别对齐芯片宽高、引脚节距、字号、外围尺寸、短线长度和主要锚点。几何与字体分别处理，不能只放大芯片和留白。
3. **保留真实关联。** 位号、数值和型号使用关联属性。网络名落在真实导线或引脚热端，不能靠“看着挨着”建立连接。多页按项目作用域和层次端口组织。
4. **局部直接接线。** 去耦、晶振、复位、驱动和采样贴近相关引脚。遵从参考的局部接线，不把每根局部线都改成标签。对外模块使用短引线和简短、对应明确的网络名。
5. **先预检再原生。** 每次改计划都运行 `scripts/check_layout.py`，修到 0 error，warning 逐条处理或写明理由，并查看草图预览。只改排版时网络和参数应保持；确需改电路时记录允许的变化。
6. **原生重开验证。** 保存后用 AD 重新读取与验证，记录实际错误和警告。必要时比较真实引脚网表中每个引脚的同网伙伴，不能只比网名或总数量。
7. **导出再审图。** 用原生打印、导出或已验证的原生绘图接口生成全图；`export` 结果中的 `text_review` 须为通过，再看全图和引脚、位号、参数等局部。问题改完重新导出，最后打包、解压核对并复开。

## 图面准则

- 普通图框、统一字体、软件习惯配色。按阅读和功能留白，不用巨大标题、卡片、渐变、装饰图标或无意义网格排列堆元件。
- 使用适合当前符号的统一栅格，连线正交、分支明确，减少折返与跨区长线。参考像素坐标不能取代引脚可连接栅格。
- 给引脚编号、网络名和参数留清楚空隙。文字互不重叠还不够，还要检查压线、压器件、挨连接点和靠近裁切边界。
- 可以复现参考的排列；明显错误的引脚、供电或参数须核实后改正，不能为外观照抄错误电路。

## 工具与结论边界

- `scripts/native_ad.py` 提供创建、原生编译/网表、原生 EMF/PNG 和本地 DelphiScript 执行入口，命令见执行文档。基础生成器不覆盖所有符号；复杂器件须使用核实的原生库、脚本或界面继续完成。
- `scripts/check_layout.py` 在调用 AD 前检查计划：栅格、悬空线端、隐式连接、按 AD 规则预测的网表与 `pin_map` 比对、文字重叠与压线、导线穿件、画面密度和参数写法，可输出草图预览。`create` 自动运行它，存在 error 时拒绝写图。
- `scripts/compare_pin_nets.py` 比较逐引脚同网关系，忽略自动网名改变，检测合网、断网、缺脚和重复归属。格式见 [核验与交付](references/verification-and-delivery.md)。
- `scripts/review_emf_text.py` 审查原生 EMF 的文字重叠、越界和文字被线条穿过；不证明图面美观或电路正确。
- 第三方重绘、生成式图片与手写二进制文件不能替代原生验证。转换先在副本上验证，未验证接口或字段标作待验证。
- 可打开、验证无错误、PCB 封装完整、实物电气可用是不同结论。未做制造检查的课程原理图不能称为可直接制板。
- 最终只交付约定文件、关键实际预览和简明复核说明；不自行增加页数、PCB、保护模块、调试模块或报告章节。

本技能采用专有商业授权，见 [LICENSE](LICENSE)；微信 1837620622，仅接受赞助和商业合作。第三方图例不属于本技能原创授权范围。
