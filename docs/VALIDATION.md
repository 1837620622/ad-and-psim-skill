# 验证说明 / Validation

本记录描述已实施的检查，不是对所有设计的质量保证。原始日志保留在维护者本机，公开仓库不包含客户工程与私有路径。

This record describes completed checks, not a guarantee for every design. Private logs and customer projects are excluded.

## 已验证环境 / Environment

| 项目 / Item | 范围 / Scope |
| --- | --- |
| Altium Designer | Enterprise 26.4.1，Windows |
| PSIM | 2026.0.0.7209，Windows 原生 API |
| Python | 3.12 |
| Agent | Codex 实际发现两项技能；其他列明宿主检查发现入口 |

## 原生工具 / Native tools

- AD 自建基础 RC 图纸：创建、编译、重开、网表比较及原生 EMF/PNG；8 个物理引脚的预期同网关系一致，0 错误、4 条警告。
- PSIM 自建 RC 电路：创建、改值、保存重开、求解、读回数据和关联文字出图。12 V、200Ω、1µF 的零初值阶跃，2000 个输出点，相对解析解最大绝对偏差约 0.0001483 V。
- 压缩包 CRC 与解压哈希一致；解压后的 AD 示例原生验证通过，PSIM 复算与原始数据一致。
- 辅助检查包括非均匀采样积分、RMS、V/I 乘积积分、储能、门极频率、无效 CSV、重复引脚及网名变化。仓库 tests 提供可移植子集，维护者另做既有工程回归。

AD tests covered native creation, compilation, reopening, pin-level connectivity and export of a basic RC example. PSIM tests covered creation, parameter updates, reopening, solving, data readback and linked-label export. Extracted copies were reopened or rerun. Portable numerical and connectivity checks are included under tests.

## 能力边界 / Limits

- AD 编译不是 SPICE/MixedSim 验证，也不是 PCB 或实物验收；保留的警告须按项目需求处理。
- PSIM RC 解析解对照只验证基础通路；复杂控制、开关损耗、磁性元件、稳态与步长收敛须针对模型检查。
- 原生导出图仍须检查压线、字体、裁切、图框和实际打印比例；字框工具不自动判定美观。
- Claude Code、ZCode、DSH 的目录适配不代表各宿主都运行过完整电路任务；Grok 需要具体宿主提供本地工具。
- 旧格式在新版打开与旧版求解器实测是不同结论；未验证的软件版本不在本记录承诺范围内。

AD compilation is distinct from circuit simulation and manufacturing acceptance. The RC check does not validate all controller models or topologies. Visual review, model-specific physics and time-resolution checks remain necessary. Host adapters and file-format compatibility do not establish end-to-end execution in every environment.

## 便携检查 / Portable checks

```powershell
python -m unittest discover -s tests -v
```

原生软件测试由可用且已授权的本地安装执行，不能在缺少软件或模型时伪造通过记录。
