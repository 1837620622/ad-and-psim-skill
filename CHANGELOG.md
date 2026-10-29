# 更新记录 / Changelog

## 1.3.0

### 新增 / Added

- 仿 Windows 原生出图（`--renderer gdi`，PNG 默认）：按仓库里的原生导出逐像素标定比例、线宽、取整和 ClearType 式文字；RC 示例与原生图尺寸相同，线条和文字像素 AD 97.8%、PSIM 97.0% 在 1 像素内对齐（不计白底）。优先用系统的 Times New Roman/Arial，没有时用字宽相同的 Liberation 字体；`env` 显示所用字体。
- `preflight`：上 Windows 前的离线预测。AD 给出预计的编译 error/warning（RC 示例预测 4 条缺少封装，与实测一致）和网表对照；PSIM 给出仿原生预览和离线预仿真。`ready_for_windows` 为 true 时没有已知阻碍。
- `presim`（PSIM）：用与 PSIM 同类的算法（节点分析 + 固定步长梯形积分）离线预仿真 R、L、C、直流源、正弦源和电压探头组成的线性电路，输出 CSV 并检查步长和时长；其他元件直接拒绝。
- 交接任务带上离线预测；Windows 运行后返回清单的 `forecast` 记录预测与实际的对照。
- `place_text` 编辑操作（AD、PSIM）：自动把压字、压线、压符号的位号和参数（AD 还包括出图框的）挪到第一个没有冲突的位置；单独挪不开时把附近的文字一起放回标准位置再摆；加 `"all": true` 时先把全部文字放回标准位置，让全图标注统一。
- 文字贴线检查（AD、PSIM）：文字离导线、引脚或符号不到 2 个单位时报 `TEXT_NEAR_LINE` warning，`place_text` 一并处理。
- `open` 命令：Windows 上用 AD 打开工程、用 PSIM 打开模型；PSIM 构建包最后自动打开做好的 psimsch（`PSIM_NO_OPEN` 可跳过）。
- 一条命令安装：`npx -y github:1837620622/ad-and-psim-skill` 把两个技能装进 Claude Code、Codex 等 Agent 的技能目录，检查 Python，自动安装可选的 Pillow（Python 3.11+；`--no-pillow` 跳过），再说明本机有没有 AD、PSIM 以及没有时怎么做；没有 Python 时给出各系统的安装办法。再运行一次就是更新，`uninstall` 卸载。
- 波形曲线和 Excel 表（PSIM）：`simulate` 和 `build.bat` 求解后把原生 CSV 画成 `waveforms.png`（每个信号一格、共用时间轴，按像素列画最小到最大值，尖峰不会被抽稀掉）并转成 `waveforms.xlsx`（全部数据和每个信号的最小、最大、末值、平均、有效值）；其他 CSV 用 `waveforms` 命令。没有 Pillow 时画 SVG；Excel 只用标准库。
- MCP 增加 `ad_preflight`、`psim_preflight`、`psim_presim`、`psim_waveforms`，共 33 个工具。

### 改进 / Changed

- 文字互相重叠改为 error：AD、PSIM 预检有文字重叠时不生成文件。
- PSIM 文字位置按原生规则估算（起点 = AREA 水平中心 - FormatFactor，字号 6/7·|FontSize|），与原生导出实测相差不超过 2 个单位；电源和探头按圆形判断压字，同一文字压同一元件只报一次。
- PSIM 电阻锯齿和 AD 引脚号位置按原生导出重新标定。
- 交付硬性规则：客户目录只放模型、原理图、仿真结果（SMV、CSV、XLSX）和波形曲线；计划和报告 JSON、Python 脚本、批处理、日志、压缩包一律不放，`--include` 点名也会被拒绝并给出 warning；`preflight/`、名字带 `presim` 的离线预仿真结果和草图也不交付。默认不再写归档目录，需要留底时加 `--archive`；`--clean` 交付后清理工作目录里的缓存（`__pycache__`、`*.pyc`、`Thumbs.db` 等）。`receive` 得到的 `final/` 可以直接交付。
- PSIM 构建包的 `build.bat` 改为调用新的 `build` 命令：先查 Python 3.10+；每一步写入 `build-report.json`，失败时窗口停住显示原因；再次双击沿用已有的 psimsch（不覆盖在 PSIM 里改过的模型），只重新求解和出图；模型建好后即使求解或出图失败也会打开。批处理只含 ASCII，中文名称经 `kit.json` 传递。
- 交接任务的 `run.bat` 先查 Python 3.11+ 和 Pillow，缺少时在启动 AD/PSIM 之前停下并给出安装命令；失败时窗口停住；再次运行时把上次没通过的结果改名为 `native-results.failed-N` 保留，已通过的结果不覆盖。
- 32 位或 ARM64 的 Python 载入 PSIM 接口失败时，报出当前 Python 的架构并提示改用与 PSIM 相同架构的 Python。
- `PSIM_DIR`、`AD_EXE` 带引号也能找到（资源管理器“复制文件地址”和 `set X="..."` 会把引号带进去）；`build.bat` 不再把 `PSIM_DIR` 作为参数转交，以反斜杠结尾的路径不会再把后面的参数吞掉。
- AD 左右朝向的电源端口名称按 AD 的规则从符号末端向外读，不再误报压在自己的符号上。
- 仿原生出图逐字排版：字宽取无微调步进，不做字距调整（与原生导出一致）；Mac 上 Pillow 没有 raqm 排版引擎时也得到与 Linux、Windows 相同的图像尺寸和像素。
- CI 的 Windows 机器上用真实 cmd.exe 运行生成的 `build.bat` 和 `run.bat`：没有 AD/PSIM 或没有 Python 时停下并说明原因、写出报告、重跑保留失败结果；中文名称、带空格路径和带引号的 `PSIM_DIR`/`AD_EXE` 都覆盖。`run.bat` 的报错输出改为 UTF-8，输出被重定向时中文报错不再出错。
- 两个 SKILL.md 增加“逐步操作（照着做）”：每一步的命令、要看的 JSON 字段、按 finding 代码的处理方法和常见错误表。
- MCP 的 `--with` 相对路径先按当前目录找，找不到再按 `mcp_server.py` 所在目录找；目录里没有 `mcp_tools.py` 时直接报错，不再启动后崩溃。
- 测试增加 MCP 改图流程（导入现有图纸、改参数、挪器件、改位号、故意压字后用 `place_text` 修好、重新生成、渲染、交付）；CI 增加“新手”任务：在 Windows、macOS、Linux 和系统自带 Python 上不克隆仓库，用 npx 一条命令安装，再照技能说明从示例计划做到交付，检查客户目录里没有 JSON、脚本和日志，最后卸载。

This release adds a Windows-look renderer calibrated against native exports, offline forecasts (`preflight`), linear PSIM pre-simulation (`presim`), automatic label placement (`place_text`) one-click opening on Windows, waveform curves with Excel tables, and a one-command `npx` setup that installs the skills, checks Python and installs Pillow. Delivery folders hold only models, drawings, results and curves, never JSON, scripts or logs. Overlapping text is now an error in both checkers. `build.bat` and `run.bat` check Python first, keep the window open on failure and can simply be run again after a fix. psimsch remains PSIM's closed format: it is written by PSIM itself on Windows and then opened automatically.

## 1.2.1

### 改进 / Changed

- AD 预检草图改用与便携渲染相同的画布：`.svg` 只需标准库，`.png` 可用 resvg-py 或 Pillow（之前帮助说支持 resvg，实际只能用 Pillow）。
- `handoff` 中途失败时清掉半成品目录，同一路径可以直接重试；依赖文件在计划目录之外时给出明确提示。
- MCP 的列表参数（`include`、字体、比较信号）可以是列表、JSON 数组文本或单个字符串，不再把字符串逐字符拆开；`*_compare` 增加 `signals` 和 `time`。
- 文档把"移动端"统一改为"Mac/Linux 准备、Windows 运行"，参考文档改名为 `references/handoff.md`；README 把交接和比较放进"使用"一节，命令统一用 `$AD`、`$PSIM` 变量写法。
- 测试文件可以单独运行。

The AD draft preview now uses the shared canvas (SVG without dependencies, PNG via resvg-py or Pillow). A failed `handoff` cleans up so the same folder can be reused. MCP list arguments accept a list, a JSON array string or a single string. Docs say "prepare on Mac/Linux, run on Windows" instead of "mobile"; the reference is now `references/handoff.md`.

## 1.2.0

### 新增 / Added

- Mac/Linux 的 `handoff` → Windows `run.bat` → Mac/Linux `receive`，自带执行脚本和显式依赖，回传原生 PNG、工程和仿真数据；逐文件核对 SHA-256。
- `compare` 比较工程/图片哈希和完整 CSV 波形，区分字节相同、数值相等与显式容差相符；不插值、不平滑。
- 可选 `resvg-py` PNG 预览后端，支持显式字体文件/目录、禁用系统字体、字体文件哈希和便携来源标记；保留 Pillow 与标准库 SVG。
- MCP 增加六项交接与比较工具，共 29 项；渲染工具支持后端与字体选项。
- 通过 Windows 卸载注册表发现自定义盘符中的 AD/PSIM 安装。

### 修复 / Fixed

- 阻止导入、编辑、截图和报告输出覆盖输入或本次生成的重要文件。
- 保留 AD 附加器件参数、支持的原生属性和原始电气类型；无法重建的模型关联明确报告，不静默丢失。
- 修正 GBK 内容被误读成 UTF-8 导致部分中文标注变化的问题。
- PSIM 移动元件时保留共用节点与探头连接，比较已知端口拓扑，意外改网时拒绝保存。
- AD/PSIM 原生文字审查失败返回非零状态，构建批处理正确停止；中文包名使用 UTF-8。
- MCP 收到形状无效的 JSON-RPC 请求后返回错误并继续会话。
- Python/Node 安装器比较完整技能内容，能发现入口文件未变时的陈旧脚本。
- 限制交付名称和目录，保留源目录原有的 manifest；npm 使用发布文件白名单，排除私有参考、厂商资料与字节码。
- 可选依赖固定 resvg-py 0.5.0 与 Pillow 13；Python 3.10 仅安装 resvg，避免自动退回有已知漏洞的旧 Pillow；Windows 原生 PNG 转换要求 Python 3.11+。

### 验证与边界 / Validation and limits

- Windows/Python 3.12 运行 84 项测试，其中 1 项非 Windows 专用检查按平台跳过；Ruff、Markdown、Node 语法、技能元数据和发布内容分别核验。
- betterleaks 未检出待发布内容的凭据泄漏；OSV 未检出固定依赖 resvg-py 0.5.0 与 Pillow 13.0.0 的已知漏洞。
- 在 Altium Designer Enterprise 26.4.1 和 PSIM 2026.0.0.7209 实际运行自建 RC 任务；接收原生 PNG 与执行端文件字节相同，PSIM 返回 CSV 与直接求解基准字节相同。
- 原生 AD 示例保留 4 项缺少封装的 warning；不将编译通过视为 PCB 制造验收。
- 离线预览仍是近似。与 Windows 原软件一致的图片和求解结果来自 Windows 原生执行；未验证其他模型、版本或 Mac/Linux 的原生求解器。

This release adds portable handoff/reception, native-result identity checks, optional resvg previews and six MCP tools. It fixes source-file overwrites, import metadata loss, shared-node disconnection, encoding, failure propagation and distribution issues. Validation uses the native Windows applications; offline rendering remains approximate. See [validation](docs/VALIDATION.md) and [preview backends](docs/preview-backends.md).
