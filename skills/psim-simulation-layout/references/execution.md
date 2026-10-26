# 原生执行入口

相对命令从本技能目录运行。将 PSIM_DIR 替换为预检确认的软件目录；本机实例见 local-evidence.md。需要本机 Python/Samples/Psim_Class.py 和 PSIM2.dll，可用性由实际初始化确认。

## 自然语言到原生模型

把描述转为拓扑、器件与模型、端口网络、参数及单位、控制方式、参考布局、工况和验收量。先用代表性小电路校准当前元件的几何与参数，再建立完整电路；新建、仅改版式、改参数复算分别留存适当基线。模型无法满足指标时分析原因，不无依据地删损耗或改目标。

| 操作 | 命令 |
|---|---|
| 验证原生 API 版本 | `python scripts/native_psim.py --psim-dir PSIM_DIR version` |
| 查真实类型与字段 | `python scripts/native_psim.py --psim-dir PSIM_DIR --report actual.json inspect model.psimsch` |
| 创建可编辑电路 | `python scripts/native_psim.py --psim-dir PSIM_DIR create assets/rc-filter-plan.json work/RC_Filter.psimsch` |
| 原生仿真和数据读回 | `python scripts/native_psim.py --psim-dir PSIM_DIR --report solve.json simulate work/RC_Filter.psimsch result` |
| 原生图纸出图 | `python scripts/native_psim.py --psim-dir PSIM_DIR --report export.json export work/RC_Filter.psimsch preview/circuit.emf` |
| 改参数并保存副本 | `python scripts/native_psim.py --psim-dir PSIM_DIR edit model.psimsch changes.json changed.psimsch` |
| 导出原生可重建脚本 | `python scripts/native_psim.py --psim-dir PSIM_DIR to-python model.psimsch model-export.py` |

输出已存在时默认拒绝覆盖，仿真使用新目录以免把旧结果当新结果。create/edit 可显式给 --overwrite，但 edit 不覆盖输入模型。export 保留完整 EMF/PNG，并附仅裁掉空白的 compact.png；紧凑裁图不改变模型布局，也不能补回原生导出中已经丢失的图元。

## JSON 建模计划

[可运行 RC 计划](../assets/rc-filter-plan.json)用于接口与解析解验证，实际项目按专业图例设计版式。

每个 element 含 type、name、attributes，attributes 直接传给当前本机 PsimCreateNewElement；不套用别的软件字段。PORTS 的第一个点、DIRECTION、AREA 和尺寸先查本机原生导出，不能用更多点强行拉伸符号。

`textlinks` 随所属元件创建，工具把实际创建返回索引写入 OWNERINDEX。每项含 AREA、FieldName、FieldIndex，字号等可覆盖本机原生导出的字体属性。FieldName 与 FieldIndex 均需与当前模型一致。位号为 Name，阻值如 Resistance；不能用静态 TEXT 写数值掩盖属性未更新。

WIRE 使用明确的正交线段，精确落到真实端口。复杂多折线、同名端、隔离测量、控制端及多页范围按本机实际元件规则核对。多行参数文件不能塞进逐行 attributes 文本，用原生文件接口处理。

参数修改 JSON：

```json
[
  {"type":"VDC","name":"V1","parameters":{"Amplitude":"12"}},
  {"type":"R","name":"R1","parameters":{"Resistance":"200"}}
]
```

本机包装器 PSIM_Element.Index 存在全部为 0 的情况。inspect 如实标出 wrapper_index 且不将其声明为可信索引，edit 用唯一的类型与名称和 PsimSetElmValue2 定位。不能把枚举序号盲传给原生几何对象；每次创建返回值中 0 合法，-1 才失败。

## 复杂模型与既有排版

使用 to-python 从当前原生文件导出位置、方向、真实端口、模型和 TEXTLINK 字段，以此校准当前版本。该转换需要本机支持 ConvertToPythonW；工具只导出，不自动运行不明代码。

检查导出脚本后，在副本中修改明确的 AREA/PORTS/线端和文字锚点；使用当前安装的 PSIM Python 模块或将导入改为本机 Psim_Class，并显式设置安装路径及新的输出位置。参数文件、子电路、DLL、设备损耗库需一并核对，转换可能丢失版本特有属性，须比较原始模型与副本。没有核验完整性时，改用原生 API/界面编辑，不能宣称无损转换。

修改布局同时移动关联局部线与文字，保持电气端口网络和参数，重新打开、导出与适当复算。若只有文字需要微调，优先调整原生关联文字锚点；不要为好看生成一张与实际模型不同的电路图片。

## 求解与结果

simulate 使用实际 PsimSimulate，保存原始 SMV 与 native.csv，检查 Time 递增、有限值和列长度。可用 --parameters 指向 JSON 传入当前 API 支持的覆盖参数；设置项与实际采样、自动步长分别核实。完成返回值只证明该次求解成功，稳态、采样和物理正确性另按参考检查。

工况扫描由 Agent 生成可追溯的参数清单并依次调用原生求解，每次保存模型/参数哈希及结果。频率、效率、纹波与功率平衡使用真实数据；实际控制芯片缺失时明确限制，不能改成独立 PI 后声称实现了芯片仿真。
