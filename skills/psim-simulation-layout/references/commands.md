# 命令与计划格式

在本技能目录下运行 `python scripts/native_psim.py <命令>`。结果以 JSON 打印到标准输出，失败时以 `{"error": ...}` 打印到标准错误并返回 1。`--report 文件` 把结果另存一份。

## 命令

| 命令 | 作用 | 系统 |
| --- | --- | --- |
| `env` | 报告系统、Python、Pillow，以及是否找到 PSIM | 任何 |
| `check PLAN [--strict]` | 排版预检 | 任何 |
| `plan-edit PLAN OPS OUT` | 按操作清单修改计划并预检 | 任何 |
| `preflight PLAN DIR` | 离线预测：排版预检（按原生规则估算文字位置）、仿原生预览、线性电路离线预仿真；`ready_for_windows` 为 false 时返回 1 | 任何 |
| `presim PLAN OUT.csv` | 离线预仿真 R、L、C、VDC、VSIN、VP 组成的线性电路（节点分析 + 固定步长梯形积分，零初始状态），另报步长和时长检查；其他元件直接拒绝 | 任何 |
| `render PLAN OUT [--scale N] [--renderer R]` | 计划渲染为 PNG/SVG；PNG 默认仿 Windows 原生出图 | 任何 |
| `package PLAN DIR [--name N]` | 生成 Windows 构建包 | 任何 |
| `build KIT [--no-open]` | 构建包入口（`build.bat` 调用）：建模、求解、出图，再用 PSIM 打开；每步写入 `build-report.json` | Windows + PSIM |
| `screenshot SOURCE OUT` | 有 PSIM 且给的是 psimsch：打开软件截窗口；否则渲染计划 | 任何 |
| `open PSIMSCH` | 用 PSIM 打开模型（不等待窗口关闭）；构建包最后会自动调用 | Windows + PSIM |
| `waveforms CSV DIR [--name N] [--signal S]... [--start T] [--end T] [--svg]` | 波形 CSV 画成曲线 PNG（每个信号一格、共用时间轴、逐像素列最小-最大包络；无 Pillow 时 SVG），并写出 XLSX（数据表 + 统计表：最小、最大、末值、按时间加权的平均值和有效值）；默认名 `waveforms` | 任何 |
| `deliver WORK OUT [--name N] [--include 通配符] [--clean] [--archive] [--dry-run]` | 生成客户目录：只放模型、图纸和仿真结果（SMV、CSV、XLSX、波形曲线），JSON、脚本、批处理、日志和压缩包一律不放；`--clean` 交付后删除缓存，`--archive` 另写过程归档和 SHA-256 清单 | 任何 |
| `handoff PLAN DIR [--name N] [--include 文件]` | 准备可校验的 Windows 原生执行任务 | 任何 |
| `receive JOB RETURNED OUT` | 校验接收原生 PNG、SMV/CSV 和模型 | 任何 |
| `compare REFERENCE CANDIDATE [--waveforms]` | 比较文件哈希或原始 CSV 数值，默认零容差 | 任何 |
| `version` | 原生 API 版本 | Windows + PSIM |
| `inspect PSIMSCH` | 读取元件类型、名称和参数 | Windows + PSIM |
| `create PLAN PSIMSCH [--overwrite]` | 按计划创建原生模型（先跑预检） | Windows + PSIM |
| `edit PSIMSCH CHANGES OUT [--overwrite]` | 改参数并另存，不覆盖输入 | Windows + PSIM |
| `simulate PSIMSCH DIR [--parameters JSON]` | 原生求解，写出 `result.smv`、`native.csv`，以及波形曲线 `waveforms.png` 和 Excel 表 `waveforms.xlsx`（结果里 `waveforms.status` 为 `written`；画图失败不影响求解结果） | Windows + PSIM |
| `export PSIMSCH OUT.emf [--dpi N]` | 原生出图：EMF、完整 PNG、去白边 PNG 和 `text_review` | Windows + PSIM |
| `to-python PSIMSCH OUT.py` | 用本机 ConvertToPythonW 导出可重建脚本（只导出不执行） | Windows + PSIM |

PSIM 安装目录按顺序查找：`--psim-dir`、环境变量 `PSIM_DIR`、Windows 卸载注册表与常见 Altair/Powersim/Siemens 目录；目录里须有 `PSIM2.dll` 和 `Python/Samples/Psim_Class.py`。支持通过注册表发现自定义盘符的安装。

输出已存在时默认不覆盖；每次仿真用新目录，避免把旧结果当新结果。

## 计划格式

```json
{
  "name": "RC_Filter",
  "elements": [
    {"type": "SIMCONTROL", "name": "", "attributes": {"POINT": "{40,50}", "TIMESTEP": "1e-6", "TOTALTIME": "0.002",
                                                      "PRINTTIME": "0", "PRINTSTEP": "1"}},
    {"type": "R", "name": "R1", "attributes": {"PORTS": "{150,100}", "DIRECTION": 0, "Resistance": 100},
     "textlinks": [{"FieldName": "Name", "FieldIndex": 0, "AREA": [160, 55, 190, 72]},
                   {"FieldName": "Resistance", "FieldIndex": 1, "AREA": [160, 72, 195, 89]}]},
    {"type": "WIRE", "name": "", "attributes": {"X1": 100, "Y1": 100, "X2": 150, "Y2": 100}}
  ]
}
```

- `attributes` 原样传给本机 `PsimCreateNewElement`，字段名以本机 PSIM 为准，不要套用别的软件的字段。
- `PORTS` 是首端口；`DIRECTION` 用 0、90、180、270。多写几个坐标不能拉长符号。
- `textlinks` 随所属元件创建，工具自动填 `OWNERINDEX`。每项要有 `AREA`、`FieldName`、`FieldIndex`，三者都须与本机模型一致。位号用 `Name`，数值用对应参数名。
- `WIRE` 只能是水平或竖直线段。多行参数文件不能写进 attributes，用原生文件接口处理。
- `name` 可选，用作构建包和模型文件名。

完整示例见 [rc-filter-plan.json](../assets/rc-filter-plan.json)：用于接口验证和解析解对照的 RC 电路，预检 0 error、0 warning。

`edit` 的修改清单：

```json
[{"type": "VDC", "name": "V1", "parameters": {"Amplitude": "12"}},
 {"type": "R", "name": "R1", "parameters": {"Resistance": "200"}}]
```

已测包装器把 `PSIM_Element.Index` 全部置 0，所以 `inspect` 标注 `index_reliable: false`，`edit` 按唯一的类型和名称调用 `PsimSetElmValue2`。创建时返回 0 是合法索引，-1 才是失败。

## 计划编辑操作

`plan-edit` 的操作清单是 JSON 数组：

| 操作 | 参数 | 说明 |
| --- | --- | --- |
| `move` | `name`（或 `type`，如 SIMCONTROL），`dx`/`dy` 或 `to` | 元件和它的文字一起移动；端口上的导线端点跟着走，斜线自动拆成不穿符号的两段 |
| `set` | `name`、`field`、`value` | 改参数 |
| `move_text` | `name`、`field`，`dx`/`dy` 或 `area` | 移动关联文字 |
| `add_element` / `remove_element` | `element` / `name` | |
| `add_wire` / `remove_wire` | `from`、`to` / `at` | `remove_wire` 删除端点在该点的导线 |
| `shift_all` | `dx`、`dy` | 整体平移 |
| `place_text` | 可选 `names`、`all` | 自动摆放关联文字：横放元件放上方或下方，竖放元件放右侧或左侧，探头名放探头旁；按原生定位规则（起点 = AREA 水平中心 - FormatFactor）计算 AREA，取第一个不压字、不压符号、不压线、不贴线的位置；逐个挪不开时把附近的文字一起放回标准位置再摆，只在问题变少时采用；没有文字问题时不改动。`"all": true` 先把文字放回标准位置（横放在上、竖放在右），再消除冲突 |

移动元件时保留共用节点上的探头和其他端口；移动前后比较已知端口的同网伙伴，发生意外断接或短接时拒绝保存。未标定器件只知道首端口，仍需原生核验。

## Windows 构建包

`package plan.json kit/` 生成：

```text
kit/
├── build.bat            # 双击：建模 → 求解 → 出图 → 打开（纯 ASCII）
├── kit.json             # 模型名称（可含中文）
├── plan.json
├── tools/               # 自包含的 Python 执行工具
├── README.txt
└── preview.render.png   # 仿原生预览（有 Pillow 时；否则 resvg-py 平滑渲染）
```

在装有 PSIM 和 64 位 Python 3.10+ 的 Windows 电脑上双击 `build.bat`（原生 PNG 另需 Python 3.11+ 和 Pillow 13），得到 `名称.psimsch`、`result\`（SMV、CSV）和 `drawing\`（EMF、PNG），最后自动用 PSIM 打开模型（设置 `PSIM_NO_OPEN` 跳过）。找不到 PSIM 时先设置 `PSIM_DIR`。psimsch 是 PSIM 的私有格式，第三方工具也要靠 PSIM 导出网表才能读，所以只能在 Windows 上由 PSIM 自己写出。

- 每一步的结果写入 `build-report.json`；失败时窗口停住显示原因（设置 `PSIM_NO_PAUSE` 不停）。没找到 Python 时提示下载地址。
- 再次双击会沿用已有的 `名称.psimsch`，不覆盖在 PSIM 里改过的模型，只重新求解和出图；要按 `plan.json` 重新建模，先删掉模型。
- 模型建好后即使求解或出图失败也会打开 PSIM，方便直接查看。
- 名称支持中文：批处理只含 ASCII，名称经 `kit.json` 交给 Python，不受控制台代码页影响。原生文字检查失败时整个构建返回失败。需要回传校验、与准备端一致的原生预览及请求对应关系时，改用 [handoff / receive](handoff.md)。

## 复杂模型与已有图

`to-python` 导出的脚本包含位置、方向、端口、模型和 TEXTLINK 字段，可用来校准当前版本。在副本里改明确的 AREA、PORTS、线端和文字位置，用本机 PSIM 的 Python 模块和新的输出路径运行。参数文件、子电路、DLL 和器件损耗库要一并核对；转换可能丢失版本特有的属性，要比较原模型和副本，不能宣称无损。只需微调文字时，优先改原生关联文字的位置。

## 截图

`render` 的 PNG 后端用 `--renderer auto|gdi|resvg|pillow` 选择。`auto` 在有 Pillow 和 Arial（或同度量的 Liberation Sans）时用 `gdi`：按 PSIM 原生导出（dpi 120）标定的像素比例 1.555 像素/单位、四周 30 像素留白、1 像素线条，文字起点按 AREA 水平中心 - FormatFactor、字号 6/7·|FontSize|，RC 示例与原生导出尺寸相同、线条和文字像素 97.0% 在 1 像素内对齐；没有时退回 resvg 或 Pillow 平滑渲染。未标定的元件画成带类型名的方框。`--font-file` / `--font-dir` 可指定字体文件；`--no-system-fonts` 只用于 resvg。渲染不求解电路；与实际 PSIM 图面一致的最终结果仍应接收 Windows 原生 PNG。

`screenshot` 在 Windows 找到 PSIM 且输入是 psimsch 时：启动 PSIM 打开模型，等窗口标题出现模型名，最大化后截取整个窗口。其他情况按计划 JSON 仿原生渲染，结果里 `source` 为 `portable_render`。截已打开的窗口：`python scripts/capture.py "PSIM" shot.png`。

## MCP

`scripts/mcp_server.py` 是只用标准库的 MCP 服务器（stdio）：

```text
python scripts/mcp_server.py                         # 只提供 PSIM 工具
python scripts/mcp_server.py --with ../../ad-schematic-layout/scripts   # 同时提供 AD 工具
npx -y github:1837620622/ad-and-psim-skill mcp       # 不用克隆仓库，需要 Node 18+
```

工具：`psim_env`、`psim_check`、`psim_preflight`、`psim_presim`、`psim_plan_edit`、`psim_render`、`psim_package`、`psim_screenshot`、`psim_create`、`psim_inspect`、`psim_edit`、`psim_simulate`、`psim_export`、`psim_measure`、`psim_waveforms`、`psim_deliver`、`psim_handoff`、`psim_receive`、`psim_compare`。计划、操作清单和修改清单参数既可以是文件路径，也可以直接写 JSON 文本；渲染和截图结果会附带图片。各客户端的配置写法见仓库 README。
