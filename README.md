# AD and PSIM Skill

**简体中文** · [English](README.en.md)

面向 Altium Designer 与 PSIM 的 AI 工程技能。通过具备本地工具能力的 Agent，将自然语言要求落实为可编辑电路、参考排版、原生验证和仿真结果。

**专有商业授权项目，非免费开源。** 使用与集成的授权条件见 [LICENSE](LICENSE)；微信：**1837620622（传康Kk）**。

## 能完成什么

| 技能 | 主要任务 | 原生输出与执行工具 |
| --- | --- | --- |
| [AD 建模与原理图排版](skills/ad-schematic-layout/SKILL.md) | 创建基础原理图、按客户参考整理布局、调用 AD 编译、比较逐引脚网络、导出图纸 | SchDoc、PrjPcb、EMF/PNG；`native_ad.py` |
| [PSIM 建模、排版与仿真](skills/psim-simulation-layout/SKILL.md) | 创建和修改原生电路、调整布局与关联标注、运行求解、读回真实参数与波形 | psimsch、SMV、CSV、EMF/PNG；`native_psim.py` |
| 工程质量检查 | 网络变化比较、文字字框筛查、按时间加权的波形测量、交付复核 | 网表差异、检查记录、统计结果 |

AI 负责理解任务、查模型、制定布局并调用工具。本包提供执行入口与工程方法；复杂器件、芯片模型和具体设计指标仍须按项目核验。AD 原理图编译与 PSIM 电路仿真是不同的检查。

## 工作方式与排版原则

1. 读取当前要求、原工程和参考图，明确本次范围及交付格式。
2. 核对软件版本、原生库、引脚、参数、坐标和导出方式，先验证代表性局部。
3. 建立可编辑电路，按功率或信号流布局，将供电、时钟、采样、补偿和反馈就近成组。
4. 保存并原生重开；AD 编译和核对网络，PSIM 按所需工况求解并读取数据。
5. 查看完整导出及关键局部，修正压线、字距、对齐、留白与裁切，再核对电气关系。
6. 按约定清单交付，打包后检查 CRC、解压哈希与原生复开。

图纸采用常规工程样式：统一栅格、正交短线、清楚连接点和关联文字，避免无意义的元件矩阵、装饰面板及大块空白。仅整理排版时，保留原有器件参数和逐端口连接。单页、单芯片等要求按当前客户任务执行。

专业风格参考见 [AD 图例观察要点](skills/ad-schematic-layout/references/professional-gallery.md) 与 [PSIM 图例观察要点](skills/psim-simulation-layout/references/professional-gallery.md)。公开仓库提供官方来源链接和原创方法，不附客户截图或厂商手册副本。

## 环境与安装

- 能读取文件、运行本地命令并查看图片的 Agent。
- Windows，以及已安装、可用并具备相应使用授权的 AD 或 PSIM；PSIM 还需随软件提供的 Python API。
- Python 3.10 或更高版本。基础创建与测量工具以标准库为主；PNG 渲染可选 Pillow，已有 SchDoc 的辅助读取可选 olefile。
- 两项技能都遵循 SKILL.md 组织方式；具体宿主的发现规则见 [兼容说明](COMPATIBILITY.md)。

以下命令供已取得相应使用授权的用户使用：

```powershell
git clone https://github.com/1837620622/ad-and-psim-skill.git
cd ad-and-psim-skill
python scripts/install_skills.py --profile common --profile claude --profile zcode
python scripts/install_skills.py --profile common --profile claude --profile zcode --check
```

只安装需要的入口即可：`common` 用于 Codex 与 DSH 的共享技能目录，`claude` 用于 Claude Code，`zcode` 用于 ZCode。Windows 创建目录联接，其他平台创建符号链接；不同内容的同名目录会保留并报冲突。安装器不安装 AD/PSIM，也不授予软件使用权。

PNG 渲染或辅助读取需要相应依赖时，可在自己的 Python 环境中安装：

```powershell
python -m pip install -r requirements-optional.txt
```

## 用自然语言调用

在已验证的 Codex 环境中，技能以套件前缀显示。重新打开会话或刷新技能列表后，可使用以下完整名称；其他 Agent 以实际技能列表为准。

**AD 建模与排版：**

```text
使用 $ad-and-psim-skill:ad-schematic-layout，读取任务书和参考图。
只制作要求的硬件，本次合成一张可编辑总图，DSP 使用一个完整符号。
按参考安排芯片、外围、字号和短引线；完成原生编译、网络检查和逐区审图后交付。
```

**PSIM 建模与自动仿真：**

```text
使用 $ad-and-psim-skill:psim-simulation-layout，按给定拓扑、额定值和控制要求建模。
功率主路在上，控制与反馈就近放在下方。运行启动、额定和必要阶跃，
核对频率、稳态、步长与功率平衡，交付可编辑模型、真实波形和清晰图纸。
```

**只整理已有工程：**

```text
按附图整理现有电路排版，保持器件、参数和逐端口连接不变。
完成后原生重开，比较网络与属性，再检查完整导出图及关键局部。
```

Grok 等模型需要由具体宿主提供本地工具；单独的聊天模型不能直接操作桌面软件。也可让宿主显式读取对应 SKILL.md，再按其相对路径调用参考和脚本。

## 可运行的基础示例

从仓库根目录创建 AD 基础 RC 图纸：

```powershell
python skills/ad-schematic-layout/scripts/native_ad.py create skills/ad-schematic-layout/assets/rc-filter-plan.json work/ad
```

PSIM 示例先设置实际安装目录，再创建、求解和导出：

```powershell
$psimDir = "C:\Path\To\PSIM"
python skills/psim-simulation-layout/scripts/native_psim.py --psim-dir "$psimDir" version
python skills/psim-simulation-layout/scripts/native_psim.py --psim-dir "$psimDir" create skills/psim-simulation-layout/assets/rc-filter-plan.json work/psim/RC_Filter.psimsch
python skills/psim-simulation-layout/scripts/native_psim.py --psim-dir "$psimDir" simulate work/psim/RC_Filter.psimsch work/psim-result
python skills/psim-simulation-layout/scripts/native_psim.py --psim-dir "$psimDir" export work/psim/RC_Filter.psimsch work/psim-preview/circuit.emf
```

将示例路径替换为实际目录。输出通常要求使用新路径，避免混用旧结果。AD 的原生编译/出图、PSIM 参数修改、关联文字和计划格式分别见 [AD 执行文档](skills/ad-schematic-layout/references/execution.md) 与 [PSIM 执行文档](skills/psim-simulation-layout/references/execution.md)。

下面是自建 RC 电路的原生接口验证图，用于展示文件生成和关联标注，复杂电路的排版质量需另行审阅。

| AD 原生导出 | PSIM 原生导出 |
| --- | --- |
| ![AD 基础 RC 原理图的原生导出](docs/images/ad-native-rc.png) | ![PSIM 基础 RC 原理图的原生导出](docs/images/psim-native-rc.png) |

## 验证状态与边界

验证环境为 AD Enterprise 26.4.1、PSIM 2026.0.0.7209 与 Python 3.12。基础流程已验证：AD 创建、编译、逐引脚网表和原生出图；PSIM 创建、改值、保存重开、求解与关联文字导出；打包后复开和复算。

AD 基础示例为 0 错误、4 条警告；这不等于零警告或可直接制板。PSIM 的 12 V RC 验证与解析解最大偏差约 0.00015 V；这项测试不覆盖所有拓扑或控制芯片。详见 [验证说明](docs/VALIDATION.md)。

便携辅助工具检查可运行：

```powershell
python -m unittest discover -s tests -v
```

Codex 的实际技能发现已验证。Claude Code、ZCode、DSH 已按发现目录适配，未逐个运行完整设计任务；Grok 依赖宿主接入。原生 Windows 后端不代表已在 macOS/Linux 上直接验证。

## 授权、联系与反馈

本项目为**公开展示源码的专有商业项目**，不提供默认的免费使用或试用许可。依法或依平台条款享有的浏览、fork 等权限不受本声明限制；超出这些权限的使用、修改、集成与再分发，按 [LICENSE](LICENSE) 和另行书面授权处理。赞助不自动产生商业授权。

- 微信：**1837620622（传康Kk）**；仅接受赞助、商业合作与授权咨询。
- 使用问题：[提交 Issue](https://github.com/1837620622/ad-and-psim-skill/issues/new/choose)，提供软件/Agent 版本、复现步骤和必要日志；不要上传凭据或客户保密工程。
- 第三方产品名称仅用于说明兼容对象与资料来源，不表示官方关联、认证或背书。第三方权利见 [声明](THIRD_PARTY_NOTICES.md)。
