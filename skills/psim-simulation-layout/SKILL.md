---
name: psim-simulation-layout
description: Build, lay out and simulate editable PSIM circuits from natural language. On any OS write a plan, pass a deterministic layout check, render a PSIM-style preview and package a Windows build kit; on Windows with PSIM create the native psimsch, run the solver, read back waveforms, verify power, efficiency and timestep, export and screenshot. 用自然语言完成 PSIM 建模、排版和原生仿真：任何系统都能预检、渲染和生成 Windows 构建包，在 Windows 上由 PSIM 写出模型、求解、读回波形并核验结果。
license: Proprietary commercial authorization required. See LICENSE.
metadata:
  compatibility: Python 3.10+ on Windows, macOS or Linux for planning, editing, handoff, reception and comparison. Native creation, simulation and export need Windows with PSIM and its Python API; receiving native PNG/SMV/CSV needs no PSIM on Mac/Linux.
---

# PSIM 建模、排版与仿真

把用户的变换器或控制要求做成可编辑的 PSIM 模型，用真实求解器跑出结果，图纸排得紧凑清楚。

## 能在哪做什么

| 操作 | 任何系统 | 需要 Windows + PSIM |
| --- | --- | --- |
| 写计划、排版预检、修改计划、仿原生渲染 | ✓ | |
| 离线预测、线性电路离线预仿真（`preflight`、`presim`） | ✓ | |
| 生成 Windows 构建包（`build.bat`） | ✓ | |
| 波形 CSV 测量、整理交付目录 | ✓ | |
| 准备交给 Windows 的任务、接收原生 PNG/SMV/CSV、比较结果 | ✓ | |
| 创建 psimsch、改参数、求解、原生出图、窗口截图 | | ✓ |

psimsch 是 PSIM 的私有二进制格式。macOS/Linux 用 `handoff` 准备可校验的任务，交给 Windows 实际 PSIM 建模、求解和出图，再用 `receive` 接收原始结果。原生预览直接显示返回的 PNG，文件字节不变。`package` / `build.bat` 仍可作为简单构建包使用。

## 工作流程

1. **列模型边界。** 分清设计值、工程假设、模型输入、仿真量和实测量；明确拓扑、额定值、控制方式、指定芯片、工况和交付格式。用户给的数值程序结果只能作对照，不能当 PSIM 结果。
2. **读排版规则。** 每次排图前读 [排版硬规则](references/drafting-rules.md)。
3. **写计划并预检。** 格式和命令见 [命令与计划格式](references/commands.md)。`check` 修到 0 error，看仿原生渲染。关联文字的实际起点 = AREA 水平中心 - FormatFactor，预检按这个规则判断压字压线；文字重叠是 error，可用编辑操作 `place_text` 自动摆放。
4. **离线预测。** `preflight` 给出仿原生预览，并对线性电路做离线预仿真（与 PSIM 同类算法），先确认参数、拓扑、步长和波形量级；`ready_for_windows` 为 true 再上 Windows。离线预仿真不是 PSIM 结果，不能交付。
5. **建模。** 有 PSIM 就直接 `create`；没有就 `package`，在 Windows 上双击 `build.bat`：PSIM 写出 psimsch、求解、出图，最后自动打开模型；失败时看 `build-report.json`，改好后再双击，已有模型会沿用。psimsch 是 PSIM 的私有格式，只能由 PSIM 写出。复杂元件先用小电路校准端口和参数，见 [建模与元件校准](references/modeling.md)。
6. **分阶段求解。** 先看启动和明显异常，再确认稳态，然后做输入/负载扫描和阶跃。时间步长与稳态见 [求解与时间基准](references/solver-and-timebase.md)。
7. **核验物理量。** 频率从实际波形测；效率只在稳态、方向一致、边界合适时才叫效率。见 [物理量与测量](references/physics-and-measurement.md)。
8. **出图与交付。** `export` 的 `text_review` 必须通过，再看全图和局部；`deliver` 生成客户目录（模型和结果）和归档目录，不打压缩包。见 [图纸、波形与交付](references/delivery.md)。

Mac/Linux 不安装 PSIM；最终图纸与仿真由 Windows 返回。仿原生渲染与 RC 示例的原生导出尺寸相同，线条和文字像素 97.1% 在 1 像素内对齐，用于提前看效果；未标定的元件画成方框，不能冒充原生图形。交接任务在 Windows 运行后会对比离线预仿真与 PSIM 波形。接收原生图和数据、拒收错配结果以及比较容差，见 [交接与结果一致性](references/handoff.md)。

## 命令速查

在本技能目录下运行，输出 JSON：

```text
python scripts/native_psim.py env                               # 本机能做什么
python scripts/native_psim.py check plan.json                   # 排版预检
python scripts/native_psim.py preflight plan.json preflight/     # 离线预测：仿原生预览 + 预仿真
python scripts/native_psim.py presim plan.json presim.csv       # 线性电路离线预仿真（不是 PSIM 结果）
python scripts/native_psim.py plan-edit plan.json ops.json new.json
python scripts/native_psim.py render plan.json view.png         # 仿原生渲染（无需 PSIM）
python scripts/native_psim.py package plan.json kit/            # Windows 构建包
python scripts/native_psim.py create plan.json model.psimsch    # Windows + PSIM
python scripts/native_psim.py simulate model.psimsch result/
python scripts/native_psim.py export model.psimsch drawing/model.emf
python scripts/native_psim.py screenshot model.psimsch shot.png # 有 PSIM 截窗口，否则渲染计划
python scripts/native_psim.py open model.psimsch                # Windows：用 PSIM 打开模型
python scripts/analyze_waveform.py result/native.csv --pin Pin --pout Pout --end 0.5 --fundamental-hz 50 --cycles 5
python scripts/native_psim.py deliver work/ delivery/ --name 项目名
python scripts/native_psim.py handoff plan.json job/
python scripts/native_psim.py receive job/ returned-results/ final/
python scripts/native_psim.py compare reference.csv final/waveforms/native.csv --waveforms
```

`scripts/mcp_server.py` 把这些命令作为 MCP 工具提供，见 [命令与计划格式](references/commands.md#mcp)。

## 底线

- 仿真结果必须来自 PSIM 求解器；控制芯片要用实际参与求解的模型，不能用独立 PI 加一个芯片名的文字框代替。
- 为了结果好看去掉损耗、漏感、饱和或启动限制，会改变设计结论；先说明模型边界再判断指标。
- Time 列只证明输出采样间隔，没有其他证据时不能当作求解器内部步长。
- 便携渲染只用于调试；对外的图用 PSIM 原生出图或真实窗口截图，并说明来源。
- 功能级仿真、原生求解、旧版本实测、硬件测量分开表述。

## 参考资料

| 需要时读 | 文件 |
| --- | --- |
| 排版数字、去 AI 味检查单、闸门 | [drafting-rules.md](references/drafting-rules.md) |
| 全部命令、计划格式、编辑操作、构建包、MCP | [commands.md](references/commands.md) |
| 模型层级、元件校准、保存前的电气审阅 | [modeling.md](references/modeling.md) |
| 时间步长、状态续算、稳态 | [solver-and-timebase.md](references/solver-and-timebase.md) |
| 变压器折算、功率、效率、PF、测量工具 | [physics-and-measurement.md](references/physics-and-measurement.md) |
| 图纸审阅、波形风格、截图称呼、交付目录 | [delivery.md](references/delivery.md) |
| 官方参考与已验证的接口经验 | [sources-and-lessons.md](references/sources-and-lessons.md) |
| Mac/Linux 交接、原生预览、哈希与波形比较 | [handoff.md](references/handoff.md) |

本技能为专有商业授权，见 [LICENSE](LICENSE)；微信 1837620622。
