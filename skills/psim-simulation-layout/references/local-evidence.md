# 已验证接口、模型与经验

## 验证环境

维护者实测 PSIM 2026.0.0.7209 的 Windows 原生 API，IsValid() 返回真。创建、参数修改、保存重开、原生求解和关联文字导出已验证，具体示例与局限见仓库 docs/VALIDATION.md。软件安装目录由当前机器预检确定。

随软件提供的 Python/Samples/Psim_Class.py 及创建、仿真、状态加载示例应优先查阅。随附手册可核对 Print Step、变压器与 FFT；帮助可能与当前功能有差异，仍须查看当前模型帮助和实机结果。

## API 用法

```python
from Psim_Class import PSIM

psim = PSIM(installation_dir)
assert psim and psim.IsValid()
version = psim.get_psim_version()
sch = psim.PsimFileOpen(model_path)
elements = psim.PsimGetElementList(sch, 1)
```

先核对当前包装器的枚举标志。已测包装器的 PSIM_Element 构造器将 Index 固定为 0，因此本包用 PsimSetElmValue2 按唯一类型和名称定位。其他版本使用元素对象或索引接口前，先确认索引对应真实对象。

TEXTLINK 按实际 OWNERINDEX、FieldIndex、FieldName 创建关联标注，模型改值后重新导出检查显示。PsimCreateNewElement 返回 0 也是有效创建索引，-1 才表示失败。

PsimFileSave 的非零返回值及重开后的属性共同证明保存成功。已测包装器中 PsimSimulate 的 Result == 0 表示失败；成功后读取 Graph，不以输出路径存在作为成功证据。

原生绘图使用已验证的 Windows DLL/GDI 路线；不表示所有版本的 Python 类都暴露相同方法。接口不适用时使用当前软件的原生打印或导出，并检查完整边界。

## 模型与物理经验

| 实例发现 | 应用方式 |
| --- | --- |
| 已测 TF_1F_1 副边 R、L 字段按原边参照；35mΩ 在 10:1 时折算为 3.5Ω | 查当前模型，用简单原生电路和解析关系确认，不从 secondary 字段名推断 |
| 个案中 200ns 设定、100ns 实际步长、Print Step=10 对应 1µs 输出 | 分列设置、原生证据和输出间隔，不套用到其他工况 |
| 状态续算依赖参数、节点与绝对时间 | 保存状态来源和模型哈希，不手改 SSF |
| 独立数值程序曲线不是 PSIM 求解 | 建立实际参与原生求解的元件和控制 |
| 旧格式在新版求解器中运行 | 分列文件格式与实际求解版本，不扩称旧版已实测 |
| 早期 RC 示例导出中仿真控制压住 Vin 名称、探头名贴住探头、电阻参数压到锯齿、电容显示 1e-06 | 仿真控制移到角落，文字区离符号至少 3，参数用后缀写法；预检和 EMF 审查都会报出这类问题 |

## 官方来源

- [Python 创建原理图示例](https://community.altair.com/discussion/25720/generating-psim-schematic-from-python-api)。
- [脚本仿真控制教程](https://2023.help.altair.com/psim-tut/tutorials/Tutorial%20-%20How%20to%20Use%20Script%20Functions.pdf)。
- [LLC 设计教程](https://2023.help.altair.com/psim-tut/tutorials/Tutorial%20-%20Resonant%20LLC%20Converter%20Design%20Using%20Power%20Supply%20Design%20Suite.pdf)。
- [LLC 损耗与效率](https://2023.help.altair.com/psim-tut/tutorials/AN007-Power%20Loss%20and%20Efficiency%20Calculation%20of%20Resonant%20LLC%20Converter.pdf)。

此前 Context7 未返回对应 PSIM 官方库，其他产品如 FluxMotor 的 API 不能代用。当前接口以官方资料、本机包装器和原生结果为依据。
