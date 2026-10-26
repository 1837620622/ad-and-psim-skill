# 命令与计划格式

在本技能目录下运行 `python scripts/native_psim.py <命令>`。结果以 JSON 打印到标准输出，失败时以 `{"error": ...}` 打印到标准错误并返回 1。`--report 文件` 把结果另存一份。

## 命令

| 命令 | 作用 | 系统 |
| --- | --- | --- |
| `env` | 报告系统、Python、Pillow，以及是否找到 PSIM | 任何 |
| `check PLAN [--strict]` | 排版预检 | 任何 |
| `plan-edit PLAN OPS OUT` | 按操作清单修改计划并预检 | 任何 |
| `render PLAN OUT [--scale N]` | 计划渲染为 PNG/SVG，样式接近 PSIM 原生导出 | 任何 |
| `package PLAN DIR [--name N]` | 生成 Windows 构建包 | 任何 |
| `screenshot SOURCE OUT` | 有 PSIM 且给的是 psimsch：打开软件截窗口；否则渲染计划 | 任何 |
| `deliver WORK OUT [--name N] [--include 通配符]` | 生成客户目录与归档目录 | 任何 |
| `version` | 原生 API 版本 | Windows + PSIM |
| `inspect PSIMSCH` | 读取元件类型、名称和参数 | Windows + PSIM |
| `create PLAN PSIMSCH [--overwrite]` | 按计划创建原生模型（先跑预检） | Windows + PSIM |
| `edit PSIMSCH CHANGES OUT [--overwrite]` | 改参数并另存，不覆盖输入 | Windows + PSIM |
| `simulate PSIMSCH DIR [--parameters JSON]` | 原生求解，写出 `result.smv` 和 `native.csv` | Windows + PSIM |
| `export PSIMSCH OUT.emf [--dpi N]` | 原生出图：EMF、完整 PNG、去白边 PNG 和 `text_review` | Windows + PSIM |
| `to-python PSIMSCH OUT.py` | 用本机 ConvertToPythonW 导出可重建脚本（只导出不执行） | Windows + PSIM |

PSIM 安装目录按顺序查找：`--psim-dir`、环境变量 `PSIM_DIR`、`C:\Altair`、`C:\Powersim`、`C:\Siemens` 和 Program Files 下名字含 PSIM 的目录；目录里须有 `PSIM2.dll` 和 `Python/Samples/Psim_Class.py`。

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

## Windows 构建包

`package plan.json kit/` 生成：

```text
kit/
├── build.bat            # 双击：create → simulate → export
├── plan.json
├── tools/               # native_psim.py、check_layout.py、psim_plan.py、review_emf_text.py
├── README.txt
└── preview.render.png   # 便携渲染预览（有 Pillow 时）
```

在装有 PSIM 和 Python 3.10+ 的 Windows 电脑上双击 `build.bat`，得到 `名称.psimsch`、`result\`（SMV、CSV）和 `drawing\`（EMF、PNG）。找不到 PSIM 时先设置 `PSIM_DIR`。

## 复杂模型与已有图

`to-python` 导出的脚本包含位置、方向、端口、模型和 TEXTLINK 字段，可用来校准当前版本。在副本里改明确的 AREA、PORTS、线端和文字位置，用本机 PSIM 的 Python 模块和新的输出路径运行。参数文件、子电路、DLL 和器件损耗库要一并核对；转换可能丢失版本特有的属性，要比较原模型和副本，不能宣称无损。只需微调文字时，优先改原生关联文字的位置。

## 截图

`screenshot` 在 Windows 找到 PSIM 且输入是 psimsch 时：启动 PSIM 打开模型，等窗口标题出现模型名，最大化后截取整个窗口。其他情况按计划 JSON 便携渲染，结果里 `source` 为 `portable_render`。截已打开的窗口：`python scripts/capture.py "PSIM" shot.png`。

## MCP

`scripts/mcp_server.py` 是只用标准库的 MCP 服务器（stdio）：

```text
python scripts/mcp_server.py                         # 只提供 PSIM 工具
python scripts/mcp_server.py --with ../../ad-schematic-layout/scripts   # 同时提供 AD 工具
npx -y github:1837620622/ad-and-psim-skill mcp       # 不用克隆仓库，需要 Node 18+
```

工具：`psim_env`、`psim_check`、`psim_plan_edit`、`psim_render`、`psim_package`、`psim_screenshot`、`psim_create`、`psim_inspect`、`psim_edit`、`psim_simulate`、`psim_export`、`psim_measure`、`psim_deliver`。计划、操作清单和修改清单参数既可以是文件路径，也可以直接写 JSON 文本；渲染和截图结果会附带图片。各客户端的配置写法见仓库 README。
