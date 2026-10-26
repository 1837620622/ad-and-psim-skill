# 第三方资料与名称 / Third-party materials and names

本项目的专有授权声明仅涉及权利人依法享有相应权利的原创内容。第三方软件、商标、资料、模型和客户内容的权利不因引用或适配而转移。

This project's proprietary notice covers only original contents for which the rights holder lawfully holds the relevant rights. References and compatibility do not transfer third-party ownership or licenses.

## 公开仓库的范围 / Public repository

- 公开仓库提供原创技能、执行工具、自建 RC 示例和官方资料链接。
- 客户工程、客户参考图、个人机器路径与原始核验日志不随仓库发布。
- 厂商教程图片、PDF、商业符号库、安装程序和运行时不随仓库分发。已有本机阅读副本保留在本机，不纳入 Git。
- docs/images 下的 RC 图片来自本项目自建测试电路：`*-native-*.png` 是原生导出，`*-render.png` 是本包的便携渲染；都不是客户电路或厂商教程截图。

The public repository includes original skills and helpers, self-contained RC examples and links to official sources. It excludes customer materials, private logs, local machine paths, vendor manual copies, commercial libraries and vendor runtimes.

## 来源 / Sources

| 来源 / Source | 资料用途 / Purpose |
| --- | --- |
| [Altium 官方原理图教程](https://resources.altium.com/p/schematic-tutorial-altium-designer-journey-thousand-pcbs) | 阅读功能流向、局部外围和文字安排 / schematic organization |
| [TI TIDM-BLPFC](https://www.ti.com/tool/TIDM-BLPFC) 与 [TIDR672](https://www.ti.com/lit/pdf/TIDR672) | 观察正式参考原理图的分区与连接 / reference schematic layout |
| [Altair PSIM 脚本仿真教程](https://2023.help.altair.com/psim-tut/tutorials/Tutorial%20-%20How%20to%20Use%20Script%20Functions.pdf) | 建模、原生仿真和波形展示方法 / modeling and simulation |

使用外部资料须遵守原权利人条款；公开可访问不等于可任意复制或商业再分发。引用链接不授予本项目向他人转授厂商资料的权利。

Altium Designer、PSIM、Texas Instruments、Codex、Claude Code、Gemini CLI、GitHub Copilot、Cursor、OpenCode、ZCode、DSH、CC Switch、Grok 等名称只用于识别软件、适配对象与资料来源。本项目独立维护，不表示官方关联、认证、赞助或背书。

External materials remain subject to their original terms. Public accessibility is not an unrestricted redistribution license. Product names identify software, compatibility targets and sources only; no official affiliation, certification, sponsorship or endorsement is implied.

排版预检内置的 Times New Roman 兼容字宽取自度量兼容字体 Liberation Serif（SIL Open Font License 1.1）的字宽数值，仓库不包含任何字体文件。

The layout checker embeds advance-width values measured from the metric-compatible Liberation Serif font (SIL Open Font License 1.1); no font files are distributed.

Pillow 等可选依赖由使用者环境提供，按各自许可使用，不随本仓库捆绑。用户仍需自行取得 AD、PSIM 和实际使用的模型或库所需的授权。
