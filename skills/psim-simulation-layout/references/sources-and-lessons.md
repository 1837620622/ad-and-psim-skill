# 参考来源与接口经验

## 官方参考

| 来源 | 看什么 | 注意 |
| --- | --- | --- |
| [Altair LLC 设计教程](https://2023.help.altair.com/psim-tut/tutorials/Tutorial%20-%20Resonant%20LLC%20Converter%20Design%20Using%20Power%20Supply%20Design%20Suite.pdf) | PDF 第 5 页功率主路在上、控制在下；第 17 页开关细节分窗 | 面板和说明箭头不进客户原理图；波形要用自己的模型求解 |
| [Altair LLC 损耗与效率](https://2023.help.altair.com/psim-tut/tutorials/AN007-Power%20Loss%20and%20Efficiency%20Calculation%20of%20Resonant%20LLC%20Converter.pdf) | PDF 第 12 页功率、驱动和热网络，就近测量 | 页脚编号有重排；参数不能当别的设计的默认值 |
| [脚本仿真控制教程](https://2023.help.altair.com/psim-tut/tutorials/Tutorial%20-%20How%20to%20Use%20Script%20Functions.pdf) | 用脚本控制仿真和参数 | 接口以本机版本为准 |
| [Python 创建原理图示例](https://community.altair.com/discussion/25720/generating-psim-schematic-from-python-api) | `PsimCreateNewElement` 的用法 | 字段名以本机为准 |

公开仓库只放官方链接，不附厂商手册和客户截图。本机可以把参考图放在本技能的 `references/images` 或 `references/professional`（不进 Git），用之前先确认文件存在和使用范围。PFC、反激等范例不是所有拓扑的固定模板。

## 已验证的接口

维护者在 PSIM 2026.0.0.7209 的 Windows 原生 API 上验证了创建、改参数、保存重开、原生求解和关联文字出图，见仓库 `docs/VALIDATION.md`。

```python
from Psim_Class import PSIM

psim = PSIM(installation_dir)
assert psim and psim.IsValid()
version = psim.get_psim_version()
sch = psim.PsimFileOpen(model_path)
elements = psim.PsimGetElementList(sch, 1)
```

- 先查随软件提供的 `Python/Samples/Psim_Class.py` 和创建、仿真、状态加载示例；随附手册可核对 Print Step、变压器和 FFT。
- 已测包装器的 `PSIM_Element` 把 Index 固定为 0，所以按唯一的类型和名称用 `PsimSetElmValue2` 改参数。
- TEXTLINK 按实际 OWNERINDEX、FieldIndex、FieldName 创建；`PsimCreateNewElement` 返回 0 是合法索引，-1 才是失败。
- `PsimFileSave` 返回非零且重开后属性正确，才算保存成功。`PsimSimulate` 的 Result == 0 表示失败；成功后读 Graph，不以输出文件存在作为成功依据。
- 原生出图用已验证的 DLL/GDI 路线；别的版本的 Python 类不一定暴露同样的方法，不适用时改用原生打印或导出。
- psimsch 是私有二进制格式（PSIM 9 起使用该扩展名），本包不直接读写它；跨系统一律通过构建包由 PSIM 写出。

## 踩过的坑

| 发现 | 做法 |
| --- | --- |
| 已测 TF_1F_1 的副边 R、L 字段按原边参照：35 mΩ 在 10:1 时填 3.5 Ω | 用简单电路和解析关系确认，不从字段名推断 |
| 个案中设定 200 ns，实际 100 ns，Print Step=10 时输出间隔 1 µs | 三个时间量分开记，不推广到别的工况 |
| 状态续算依赖参数、节点和绝对时间 | 保存状态来源和模型哈希，不手改 SSF |
| 独立数值程序的曲线不是 PSIM 求解 | 建立实际参与原生求解的元件和控制 |
| 旧格式在新版求解器里运行 | 文件格式和实际求解版本分开写 |
| 早期 RC 示例导出中仿真控制压住 Vin、探头名贴着探头、电阻参数压到锯齿、电容显示 1e-06 | 仿真控制放角落，文字区离符号至少 3，参数用后缀写法；预检和 EMF 审查都能查出 |

Context7 检索不到对应的 PSIM 官方库，FluxMotor 等其他产品的 API 不能拿来代用。
