# 验证记录 / Validation

这里记录实际做过的检查，不是对所有设计的质量保证。原始日志留在维护者本机，仓库不含客户工程和私有路径。

This records the checks actually performed; it is not a guarantee for every design.

## 原生验证 / Native validation

| 项目 | 环境 | 结果 |
| --- | --- | --- |
| AD 自建 RC 图纸（上一版示例） | Altium Designer Enterprise 26.4.1，Windows | 创建、编译、重开、逐引脚网表、原生 EMF/PNG；8 个物理引脚的同网关系一致；0 error、4 warning |
| PSIM 自建 RC 电路（上一版示例） | PSIM 2026.0.0.7209 原生 API，Windows | 创建、改参数、保存重开、求解、读回数据、关联文字出图；12 V、200 Ω、1 µF 零初值阶跃，2000 个输出点，与解析解最大偏差约 0.0001483 V |
| 交付副本复开 | 同上 | 交付副本中的 AD 示例原生验证通过，PSIM 复算与原始数据一致 |
| 技能发现 | Codex | 两项技能都被发现 |

上一版示例的原生导出：[AD](images/ad-native-rc.png)、[PSIM](images/psim-native-rc.png)。

## 待在 Windows 上复验 / Pending native re-check

本次改动的以下部分在 Linux 上做了可移植测试，还需要在装有软件的 Windows 上跑一遍：

| 改动 | 复验命令 | 要看什么 |
| --- | --- | --- |
| 新的 AD 示例布局；无源件热端对齐栅格；默认文字位置；导线在热端分段；CFB 空目录项；分区数随图幅变化 | `native_ad.py create assets/rc-filter-plan.json work` → `verify work/RC_Filter.PrjPcb out --expected work/expected.json` → `export work/RC_Filter.SchDoc drawing` | 编译 0 error，拓扑一致，`text_review.passed`，warning 数量 |
| DelphiScript 失败时写 `Failed=` | 用不存在的文档路径运行 `export` | 立即报错而不是等到超时 |
| PSIM 示例的文字位置、仿真控制位置、`1u` 写法 | `native_psim.py package assets/rc-filter-plan.json kit`，在 kit 里运行 `build.bat` | 创建、求解成功；`1u` 被解析为 1 µF；`text_review.passed` |
| AD/PSIM 安装目录自动查找 | `native_ad.py env`、`native_psim.py env` | 能找到本机 X2.EXE 和 PSIM 目录 |
| 窗口截图 | `native_ad.py screenshot X.SchDoc shot.png`，`native_psim.py screenshot X.psimsch shot.png` | 截到已加载文档的主窗口 |

复验通过后，用新的原生导出替换上表链接的两张旧图。

## 可移植测试 / Portable tests

```bash
python -m unittest discover -s tests -v
```

不需要 AD 或 PSIM，在 Linux 上用 Python 3.10 和 3.13 运行，覆盖：

- 排版预检：两项示例 0 error、0 warning；悬空线、浮空标号、离栅格热端、隐式短接、不可编码字符等结构错误；文字重叠、穿件导线、四向连接、浮动标题、稀疏图面等版面问题；PSIM 的文字压符号、导线穿符号、仿真控制位置、参数写法。
- SchDoc 读写：标准库读写复合文档；二进制引脚记录解码；示例生成文件的 SHA-256 固定（跨系统字节一致）；导入后重建的记录完全相同；各缩放比例下无源件热端在栅格上。
- 编辑：移动器件后导线正交重连；PSIM 移动元件后导线绕开符号。
- 便携渲染：输出 PNG 和 SVG。
- EMF 审查：映射模式换算、文字被线穿过、圆形压字、单个字符不误报。
- 波形测量：非均匀采样积分、RMS、V/I 乘积积分、储能、门极频率、无效 CSV。
- MCP 服务器协议、两个安装器、交付目录分类、Windows 构建包。
- README 中的命令流程，包括输出目录不存在时自动创建。

另做过的人工对照：二进制引脚解码用公开的 AD 库文件样本核对过名称、编号、长度和方向；AD 便携渲染与上一版原生导出逐区对比，分区、连接点、地符号、引脚名和引脚号位置一致；PSIM 便携渲染与上一版原生导出对比，符号形状和位置一致，文字字形比原生略宽。

## 边界 / Limits

- AD 编译不是 SPICE/MixedSim 仿真，也不是 PCB 或实物验收；保留的 warning 要按项目处理。
- PSIM 的 RC 解析解对照只验证基础通路；复杂控制、开关损耗、磁性元件、稳态和步长收敛要针对模型检查。
- 原生出图仍要人工看压线、字体、裁切、图框和实际打印比例；工具不判定美观。
- 便携渲染是近似，不是原生导出。
- 其他宿主只按目录适配，没有逐个运行完整电路任务。
- 旧格式在新版中打开和旧版求解器实测是不同结论；没验证过的软件版本不在承诺范围内。
