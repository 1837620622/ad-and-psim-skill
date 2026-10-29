# 验证记录 / Validation

这里记录实际做过的检查，不是对所有设计的质量保证。原始日志留在维护者本机，仓库不含客户工程和私有路径。

This records the checks actually performed; it is not a guarantee for every design.

## 原生验证 / Native validation

| 项目 | 环境 | 结果 |
| --- | --- | --- |
| AD 当前 RC 图纸 | Altium Designer Enterprise 26.4.1，Windows | 创建、编译、重开、逐引脚网表、原生 EMF/PNG；8 个物理引脚的同网关系一致；0 error、4 个缺少封装的 warning；原生文字审查通过 |
| PSIM 当前 RC 电路 | PSIM 2026.0.0.7209 原生 API，Windows | 10 V、100 Ω、1 µF 零初值阶跃；2000 个输出点；与 RC 解析解最大偏差约 0.000488484 V；原生文字审查通过 |
| AD 交接任务执行与接收 | 自包含任务的 `run.bat`，同上 Windows 环境 | 从准备到原生编译、网表与出图全部通过；准备和执行端 SchDoc 字节相同；接收 PNG 与原生导出哈希相同 |
| PSIM 交接任务执行与接收 | 自包含任务的 `run.bat`，同上 Windows 环境 | 原生创建、求解、出图及接收全部通过；返回 CSV 与直接调用 PSIM 的基准文件字节相同，2000 点、全部列、零容差比较通过 |
| 修复后的共用节点移动 | PSIM 原生 API | 移动 C1 后 Vout 探头保持连接，原生求解通过，全部波形与基准数值相等 |
| 中文批处理与中文原理图标注 | PSIM / AD，同上环境 | 中文包名完成创建、求解及出图；GBK 的“漏”字读写和 AD 原生文字保持正确 |
| 附加参数导入重建 | AD，同上环境 | 隐藏 Tolerance=1% 参数保留；重建图纸原生编译、逐引脚网表通过 |
| 原生出图失败传播 | AD / PSIM，同上环境 | 故意重叠位号和数值，两个 export 均返回 1；PSIM 批处理返回失败，不再打印 Done |
| 自动发现与窗口截图 | 自定义盘符安装，同上环境 | 卸载注册表发现 X2.EXE 和 PSIM；实际打开 RC 文档并截到真实软件窗口 |
| 技能发现 | Codex | 两项技能都被发现 |

当前示例的原生导出：[AD](images/ad-native-rc.png)、[PSIM](images/psim-native-rc.png)。AD 的 4 条封装 warning 不属于 PCB 制造验收通过。

## 一致性证据 / Identity evidence

AD 基础示例生成的 SchDoc SHA-256：

```text
bd8a32b1df5075a3ebedfcc4c89ce5359bd79a0842b54bbfa27505f85180cedc
```

PSIM 当前 RC 基准 CSV 与交接任务返回 CSV 的 SHA-256 相同：

```text
08aca6ea5b6d6d6c5ba574f3b36784dd73c2f41c2b89ac13b91c9c44c87931a5
```

以上只针对该示例、当前模型与已列明的软件版本。原始 Time 从 1 µs 到约 2 ms，输出间隔约 1 µs；它是输出采样证据，不单独证明求解器内部步长。

接收器复制 Windows 原生图片，不在 Mac/Linux 上重绘。离线便携渲染仍有字体和未标定符号差异，不用它声称与所有原生图逐像素相同。

## 可移植测试 / Portable tests

```bash
python -m unittest discover -s tests -v
```

无需 AD 或 PSIM。CI 配置 Windows、macOS、Linux 与 Python 3.10/3.13；1.2.0 在本机 Windows/Python 3.12 运行 84 项测试，1.3.0 的修改在 Linux 上用 Python 3.10 和 3.13 运行 139 项（其中 3 项只在 Windows 上用 cmd.exe 实际运行 `build.bat` 和 `run.bat`，由 CI 的 Windows 机器执行；Linux 上 3.13 装 Pillow 13 和 resvg-py 时其余全部运行，Python 3.10 没有 Pillow 和 resvg-py，另跳过仿原生出图等 7 项）。覆盖：

- 排版预检：两项示例 0 error、0 warning；悬空线、浮空标号、离栅格热端、隐式短接、不可编码字符等结构错误；文字重叠、穿件导线、四向连接、浮动标题、稀疏图面等版面问题；PSIM 的文字压符号、导线穿符号、仿真控制位置、参数写法。
- SchDoc 读写：标准库读写复合文档；二进制引脚记录解码；示例生成文件的 SHA-256 固定（跨系统字节一致）；导入后重建的记录完全相同；各缩放比例下无源件热端在栅格上。
- 编辑：移动器件后导线正交重连；PSIM 移动元件后导线绕开符号。
- 便携渲染：Pillow、resvg PNG 和 SVG；显式字体配置、PNG 来源信息与同一输入重复输出；后端比较见 [预览评测](preview-backends.md)。
- EMF 审查：映射模式换算、文字被线穿过、圆形压字、单个字符不误报。
- 波形测量：非均匀采样积分、RMS、V/I 乘积积分、储能、门极频率、无效 CSV。
- MCP 服务器协议（含 `--with` 相对路径）、两个安装器、交付目录分类、Windows 构建包；`PSIM_DIR`、`AD_EXE` 带引号时也能找到软件。
- README 中的命令流程，包括输出目录不存在时自动创建。
- 输入输出同路径保护、报告不得覆盖已有文件或本次生成的计划/检查文件、附加参数保留、模型关联拒绝静默丢失、GBK/UTF-8 文字解码。
- 交接任务自包含、显式依赖、原生结果接收、文件被改动/请求错配/失败结果/路径越界拒收；计划目录外的依赖被拒绝；准备失败后目录可重用。
- AD 预检草图输出 SVG（只用标准库）和 PNG（resvg-py 或 Pillow）。
- 仿原生出图：AD、PSIM 的 RC 示例与仓库里的 Windows 原生导出逐像素比较，图像尺寸相同，线条和文字像素至少 95% 在 1 像素内对齐（实测 AD 97.8%、PSIM 97.0%，不计白底）；Pillow 有无 raqm 排版引擎出图逐字节相同（macOS 常没有 raqm）；方法与前后对比见 [预览后端](preview-backends.md)。
- PSIM 文字定位：按"起点 = AREA 水平中心 - FormatFactor、字号 6/7·|FontSize|"估算的 7 段文字，与原生导出实测位置相差不超过 2 个单位；文字离电源太近时报出。
- 文字重叠：两项预检把文字互相重叠列为 error，文字离线条不到 2 个单位报 `TEXT_NEAR_LINE`；`place_text` 把故意弄乱的 AD、PSIM 示例修到 0 个文字问题，没有问题的计划不改动，`all` 把挪开的文字放回标准位置。另在测试之外做过随机压力试验：AD 954 个随机弄乱的版面（其中 478 个器件间距只有 80–100、文字偏移达 ±50）、PSIM 1181 个（其中 590 个元件间距只有 70–90、文字偏移达 ±60），`place_text` 全部修到 0 个文字问题；`all` 放回标准位置后 AD 120 个、PSIM 200 个也都没有文字问题；行距只有 20 的 AD 梯形网络也修到 0 个文字问题。
- 离线预仿真：RC 阶跃与解析解最大偏差小于 1e-4 V（实测约 3e-5 V），RL 阶跃电流、RC 正弦稳态幅值与解析值一致；遇到开关等元件拒绝；步长过粗报出。
- 离线预测：AD 示例预测 0 个编译 error、4 条缺少封装的 warning，与 Windows 实测一致；PSIM 示例预检、预览和预仿真都通过；离线预仿真与原生波形的对照记录。
- 交付：客户目录只有模型、原理图、仿真结果和波形曲线；计划和报告 JSON、脚本、批处理、日志、压缩包即使用 `--include` 点名也不进；`preflight/`、presim 文件和草图不交付；默认不写归档，`--archive` 才写；`--clean` 只删缓存，不删 History 和 `*.bak`；`receive` 的 `final/` 可直接交付。
- 波形曲线和 Excel 表：20 万点里的单个尖峰保留在曲线和统计里；刻度文字（如 `2.5`、`25m`、`Time (ms)`）；XLSX 用标准库读回，每个数值与 CSV 相同，超过行数上限时接着写下一张表；同一输入重复生成的 PNG 和 XLSX 逐字节相同；时间窗和信号选择；时间倒序的 CSV 报错且不留半成品；没有 Pillow 时写 SVG；presim 曲线不交付；`simulate`、构建包和 MCP 都生成。
- MCP 改图流程：一个服务器进程里导入现有 SchDoc、改参数、挪器件、改位号，故意把文字压在一起后预检报 `TEXT_OVERLAP`，`place_text` 修到 0 error，重新生成后读回确认改动都在，渲染出 PNG，交付时客户目录只有 PrjPcb 和 SchDoc、缓存被清理；PSIM 同样改参数、挪元件、改文字、自动摆放，再把离线预仿真画成曲线和 Excel 表，生成构建包。
- 一条命令安装：临时主目录里运行 `bin/cli.mjs`，技能装进各 Agent 的目录（检测到 ZCode 时也装），Python 安装器的检查通过，再运行一次仍然通过。
- 文件哈希、完整 CSV、零容差与显式容差、时间网格差异和无效数据。
- 安装器检查脚本变更；npm 包排除私有参考和字节码；交付保留输入目录已有的 manifest。

另做过人工对照：二进制引脚解码用公开的 AD 库文件样本核对过名称、编号、长度和方向；当前两张原生全图与真实窗口均查看过。便携图用于布局近似，不能替代原生图片。

CI 另有“新手”任务，在 Windows、macOS、Linux 上各跑一遍（Linux 再加一次系统自带、不允许 pip 安装的 Python）：不克隆仓库，`npx` 安装本次提交，检查自动装上的 Pillow、`check`、`doctor` 和 MCP 工具列表；再只用装好的技能目录，照 SKILL.md 的步骤把 AD、PSIM 示例从预检、改图、离线预测、生成、渲染做到交付，确认客户目录里没有 JSON、脚本、批处理和日志；最后卸载。CI 没有 PSIM，PSIM 交付一步用占位模型代替 `build.bat` 的产物。

MCP 1.2.0 已在 Windows 上完成 29 工具枚举（1.3.0 增加到 33 个，协议测试和改图流程在 Linux 上通过），并真实调用任务准备、AD/PSIM 原生结果接收和 CSV 比较；原生图片随 MCP 结果返回。Ruff、Markdown、技能元数据和打包白名单分别检查。

安全检查使用 betterleaks 1.9.0 扫描 Git 历史与待发布文件，没有检出凭据泄漏；OSV Scanner 2.7.0 扫描固定依赖 resvg-py 0.5.0、Pillow 13.0.0，没有检出已知漏洞。旧 Pillow 的扫描有命中，因此 Python 3.10 的可选安装只包含 resvg，Windows 原生 PNG 转换使用 Python 3.11+。扫描结论只覆盖所列版本和公开扫描范围。

## 边界 / Limits

- AD 编译不是 SPICE/MixedSim 仿真，也不是 PCB 或实物验收；保留的 warning 要按项目处理。
- PSIM 的 RC 解析解对照只验证基础通路；复杂控制、开关损耗、磁性元件、稳态和步长收敛要针对模型检查。
- 原生出图仍要人工看压线、字体、裁切、图框和实际打印比例；工具不判定美观。
- 仿原生渲染是按参考导出标定的预测图，不是原生导出：文字抗锯齿不能逐像素复现；原生导出的像素比例取决于导出机器的设置；未标定的 PSIM 元件画成方框。
- 离线预仿真只覆盖线性元件，与 PSIM 属同类算法但不是 PSIM；初始条件、开关处理和数值细节以 PSIM 为准。
- psimsch 是 PSIM 的私有格式，本包不直接写；Windows 上由 PSIM 原生接口写出后自动打开。
- 其他宿主只按目录适配，没有逐个运行完整电路任务。
- 旧格式在新版中打开和旧版求解器实测是不同结论；没验证过的软件版本不在承诺范围内。
- 未逐个演练所有 DelphiScript 异常、取消组合以及所有厂商库器件；复杂工程仍须按当前任务进行原生验证。

## 待在 Windows 上复验 / Pending native re-check

1.3.0 的以下部分只在 Linux 上做了可移植测试：

| 改动 | 复验方法 | 要看什么 |
| --- | --- | --- |
| 构建包最后自动用 PSIM 打开模型；`open` 命令 | 双击 `build.bat`；`native_ad.py open X.PrjPcb` | PSIM、AD 窗口打开且已载入模型；设置 `PSIM_NO_OPEN` 时不打开 |
| 交接任务的 `forecast` 对照 | `handoff` → `run.bat` → `receive` | AD 预计与实际 warning 数一致；PSIM 离线预仿真与原生波形的最大偏差 |
| macOS 上用真 Times New Roman/Arial 的仿原生出图 | `render` 后与原生导出比较 | 尺寸相同，线条和文字对齐率不低于 Linux |
| `build.bat` 改走 `build` 命令 | 中文名称的构建包双击两次；再故意让一步失败 | 两次都通过且第二次沿用模型；失败时窗口停住、`build-report.json` 记下原因、模型仍被打开 |
| `run.bat` 先查依赖并可重跑 | 未装 Pillow 时双击；装好后再双击 | 启动软件前停下并提示安装命令；第二次通过，上次结果留在 `native-results.failed-1` |
