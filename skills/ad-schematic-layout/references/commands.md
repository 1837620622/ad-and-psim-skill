# 命令与计划格式

在本技能目录下运行 `python scripts/native_ad.py <命令>`。结果以 JSON 打印到标准输出，失败时以 `{"error": ...}` 打印到标准错误并返回 1。全局参数 `--report 文件` 把结果另存一份；`--timeout 秒` 控制等待 AD 的时间（默认 180）。

## 命令

| 命令 | 作用 | 系统 |
| --- | --- | --- |
| `env` | 报告系统、Python、Pillow，以及是否找到 AD | 任何 |
| `check PLAN [--preview FILE] [--strict]` | 排版预检；`--strict` 时 warning 也算失败；草图 `.svg` 只需标准库，`.png` 需要 resvg-py 或 Pillow | 任何 |
| `create PLAN DIR` | 写出 `名称.SchDoc`、`名称.PrjPcb`、`expected.json`、`layout-check.json` | 任何 |
| `import SCHDOC PLAN [--allow-partial]` | 现有 SchDoc 转计划；有无法表示的图元时默认不写出 | 任何 |
| `edit PLAN OPS PLAN_OUT` | 按操作清单修改计划并预检 | 任何 |
| `preflight PLAN DIR` | 离线预测：排版预检、预测网表、预计的编译 warning（缺封装）、仿原生预览；`ready_for_windows` 为 false 时返回 1 | 任何 |
| `render SOURCE OUT [--scale N] [--renderer R]` | SchDoc 或计划渲染为 PNG/SVG；PNG 默认仿 Windows 原生出图 | 任何 |
| `screenshot SCHDOC OUT` | 有 AD：打开软件截取窗口；没有：改用仿原生渲染 | 任何 |
| `open PRJPCB/SCHDOC` | 用 AD 打开工程或图纸（不等待窗口关闭）；Mac/Linux 生成的文件拷过去即可直接打开 | Windows + AD |
| `verify PRJPCB DIR [--expected JSON]` | 在副本上原生编译，导出逐引脚网表并比较 | Windows + AD |
| `export SCHDOC DIR [--dpi N]` | 原生导出 EMF 与 PNG，附文字审查 `text_review` | Windows + AD |
| `run-script PAS PROCEDURE` | 运行本地 DelphiScript | Windows + AD |
| `deliver WORK OUT [--name N] [--include 通配符]` | 生成客户目录与归档目录 | 任何 |
| `handoff PLAN DIR [--name N] [--include 文件]` | 准备可交给 Windows 原生执行的完整任务 | 任何 |
| `receive JOB RETURNED OUT` | 验证接收原生 PNG、工程与结果；不重绘 | 任何 |
| `compare REFERENCE CANDIDATE [--waveforms]` | 比较文件字节或 CSV 数值，默认零容差 | 任何 |

AD 程序按顺序查找：`--ad-exe`、环境变量 `AD_EXE`、Windows 卸载注册表及常见 Altium 目录。注册表发现兼容自定义盘符；多个有效安装中选择版本号最高的一个。

`check_layout.py`、`review_emf_text.py`、`compare_pin_nets.py`、`deliver.py`、`capture.py` 也可以单独运行，参数见各自的 `--help`。

## 计划格式

```json
{
  "name": "RC_Filter", "units": "10mil", "grid": 10, "canvas": [420, 240],
  "parts": [
    {"kind": "component", "ref": "J1", "value": "INPUT", "body": [60, 130, 90, 160],
     "pins": [{"number": "1", "name": "VIN", "at": [90, 150], "direction": "right"}]},
    {"kind": "R", "ref": "R1", "value": "10k", "at": [180, 150]},
    {"kind": "C", "ref": "C1", "value": "100nF", "at": [240, 120], "vertical": true}
  ],
  "wires": [["J1.1", "R1.1"], ["R1.2", [240, 150], [300, 150]]],
  "labels": [{"name": "VIN", "at": [120, 150]}],
  "power_ports": [{"name": "DGND", "at": "C1.2", "ground": true}],
  "pin_map": {"J1.1": "VIN", "R1.1": "VIN"}
}
```

| 字段 | 说明 |
| --- | --- |
| `units` | 必须是 `"10mil"`；坐标向右、向上 |
| `canvas` | 图纸宽高；`border`（默认 true）在距边 20 处画图框 |
| `grid`、`font` | 默认 10 和 1（9 pt Times New Roman，全部器件文字共用） |
| R/C/L/Y | `ref`、`value`、`at`（中心，须在栅格上）、`vertical`、`symbol_scale`（默认 0.5，热端始终在栅格上） |
| `component` | `body` 矩形与 `pins`；每脚 `number`、`name`、`at`（框边上的点）、`direction`（right/up/left/down）、`electrical`（input/output/bidirectional/open_collector/passive/power）；`pin_length` 默认 20；`expected_pin_count` 可选 |
| `designator_at`、`comment_at` | 覆盖默认文字位置 |
| `wires` | 折线点列表；点可写 `"R1.1"`（引脚热端）或坐标。斜线默认自动补成正交折线（`"autoroute": false` 关闭） |
| `labels` | `name`、`at`，可选 `orientation` |
| `power_ports` | `name`、`at`（坐标或引脚）、`ground`；可选 `orientation`、`style` |
| `junctions`、`texts` | 手动连接点；必要的说明文字（标题写进图签） |
| `pin_map` | 引脚到网络的预期，来自设计意图；预检和 `verify` 都拿它比较拓扑 |

示例计划见 [rc-filter-plan.json](../assets/rc-filter-plan.json)：常规接插件比例、就近地符号，预检 0 error、0 warning。

基础生成器只画矩形符号器件和 R/C/L/Y。运放、MOSFET 等需要专用图形和模型的器件，用本机核实过的原生库和 AD API 完成，不要都画成方框。

## 编辑操作

`edit` 的操作清单是 JSON 数组，按顺序执行：

| 操作 | 参数 | 说明 |
| --- | --- | --- |
| `move` | `ref`，`dx`/`dy` 或 `to` | 器件和它的文字一起移动；引用其引脚的导线自动正交重连 |
| `set_value` | `ref`、`value` | 改参数 |
| `move_text` | `ref`、`field`（designator/comment）、`at` | 改文字位置 |
| `rename` | `ref`、`to` | 改位号，导线、标号、`pin_map` 一起更新 |
| `add_part` / `remove_part` | `part` / `ref` | 删除器件时连到它的导线和标号一起删除 |
| `add_wire` / `remove_wire` | `points` / `index` 或 `touching` | |
| `add_label` / `remove_label` | `name`、`at` | |
| `add_power_port` / `remove_power_port` | `name`、`at`、`ground` | |
| `set_canvas` / `shift_all` / `fit_canvas` | `canvas` / `dx`、`dy` / `margin` | `fit_canvas` 按内容缩放画布并居中 |
| `place_text` | 可选 `refs`、`all` | 自动摆放位号和参数：对压字、压线、贴线、出图框、落进别的器件框的文字依次试上方叠放、下方叠放、上下分开、右侧、左侧，取第一个没有问题的位置；逐个挪不开时把附近的文字一起放回标准位置再摆，只在问题变少时采用；没有文字问题时不改动。`"all": true` 先把这些器件的文字放回生成器的标准位置，再消除冲突 |
| `set_pin_map` | `pin_map` | 改预期连接 |

`import` 生成的计划带 `pin_map`，记录导入时的连接；只改排版时，预检会确认连接没有变。导入只支持本生成器能重建的图元，带库图形或多部件的器件会列在 `unsupported` 里。

附加器件参数和可表示的元数据保留；无法重建的模型关联会报告为 unsupported，默认不写计划。导入、编辑和截图不允许输出覆盖输入。`export` 的文字检查未通过时返回非零状态，MCP 同样报告失败。

交给 Windows 的任务、原生预览接收和一致性等级见 [handoff.md](handoff.md)。

## 原生脚本

`verify` 和 `export` 把文档复制到 ASCII 临时目录，生成 DelphiScript 并通过 AD 命令行执行。脚本写出含 `Complete` 的状态文件表示完成，写出 `Failed=原因` 表示失败，启动器会立刻报错，不用等超时。自定义脚本用同一约定：

```pascal
Procedure Main;
Var Status : TStringList;
Begin
    { 在这里做已核实的原生编辑 }
    Status := TStringList.Create;
    Status.Add('Complete');
    Status.SaveToFile('__STATUS__');
    Status.Free;
End;
```

中文参数通过 UTF-16 输入文件传递，脚本本体保持 ASCII。`verify` 的编译调用可能涉及工作区里其他已打开的工程，报告只统计目标工程。`export` 用原生 `RedrawToDC`，只修正 EMF 容器的物理尺寸字段，绘图记录不变。

## 截图

`render` 的 PNG 后端用 `--renderer auto|gdi|resvg|pillow` 选择。`auto` 在有 Pillow 和 Times New Roman/Arial（或同度量的 Liberation）时用 `gdi`：按 Windows 原生导出标定的像素比例（约 2.16 像素/单位）、线宽、取整和 ClearType 式文字，RC 示例与原生导出尺寸相同、线条和文字像素 97.8% 在 1 像素内对齐；没有时退回 resvg 或 Pillow 平滑渲染。`--scale` 不给时按后端取默认值。`--font-file` / `--font-dir` 可指定字体文件（gdi 按字体族名替换，resvg 加入字体库）；`--no-system-fonts` 只用于 resvg。JSON 记录后端和所用字体。与实际 AD 图面一致的最终结果仍应接收 Windows 原生 PNG。

`screenshot` 在 Windows 找到 AD 时：启动 AD 打开文档，等标题出现文档名，最大化，发送 Ctrl+PageDown（适合文档），截取整个窗口为 PNG。其他情况改用仿原生渲染，结果里 `source` 为 `portable_render`。要截已经打开的窗口：`python scripts/capture.py "Altium" shot.png`。

## MCP

`scripts/mcp_server.py` 是只用标准库的 MCP 服务器（stdio），每次调用都在子进程里运行上面的命令。

```text
python scripts/mcp_server.py                         # 只提供 AD 工具
python scripts/mcp_server.py --with ../../psim-simulation-layout/scripts   # 同时提供 PSIM 工具
npx -y github:1837620622/ad-and-psim-skill mcp       # 不用克隆仓库，需要 Node 18+
```

工具：`ad_env`、`ad_check`、`ad_preflight`、`ad_create`、`ad_import`、`ad_edit`、`ad_render`、`ad_screenshot`、`ad_verify`、`ad_export`、`ad_deliver`、`ad_handoff`、`ad_receive`、`ad_compare`。计划和操作清单参数既可以是文件路径，也可以直接写 JSON 文本；渲染和截图结果会附带图片。各客户端的配置写法见仓库 README。
