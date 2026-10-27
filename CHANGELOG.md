# 更新记录 / Changelog

## 1.2.0

### 新增 / Added

- Mac/Linux 的 `handoff` → Windows `run.bat` → 移动端 `receive`，自带执行脚本和显式依赖，回传原生 PNG、工程和仿真数据；逐文件核对 SHA-256。
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
