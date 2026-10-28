# 兼容说明 / Compatibility

两个技能采用 [Agent Skills 开放格式](https://agentskills.io/specification)：SKILL.md 加相对路径的参考、脚本和示例；指令是普通 Markdown，核心脚本只用 Python 标准库（便携 PNG 可选 resvg-py 或 Pillow，Windows 原生 EMF 转 PNG 需要 Pillow）。能不能用取决于**宿主**而不是模型品牌：宿主要让模型读本地文件、运行命令、查看图片。满足这三点，Claude、GPT、Gemini、Grok、DeepSeek、Qwen、Kimi、GLM 等模型都按同一套指令工作。

Both skills follow the Agent Skills format. Compatibility depends on the host, not the model vendor: the host must let the model read local files, run commands and inspect images.

## 宿主与目录 / Hosts and directories

| 宿主 / Host | 用户级目录 / User directory | 安装器 Agent 名 |
| --- | --- | --- |
| Codex | `~/.agents/skills` | `universal` 或 `codex` |
| Gemini CLI | `~/.agents/skills`（或 `~/.gemini/skills`） | `universal` 或 `gemini` |
| GitHub Copilot（CLI、VS Code、JetBrains、云端） | `~/.agents/skills`、`~/.copilot/skills`、`~/.claude/skills` | `universal` 或 `copilot` |
| Cursor | `~/.agents/skills`、`~/.cursor/skills`、`~/.claude/skills` | `universal` 或 `cursor` |
| OpenCode | `~/.agents/skills`、`~/.claude/skills`、`~/.config/opencode/skills` | `universal` 或 `opencode` |
| Claude Code | `~/.claude/skills`，或本仓库的插件清单 | `claude` |
| ZCode | `~/.zcode/skills` | `zcode` |
| DSH / DeepSeek Harness | `.agents/skills`、`.dsh/skills` | `universal` |
| 其他宿主 / Others | 由宿主决定 | 见下方"手动加载" |

Codex 的技能发现实际验证过；其他宿主按官方文档的目录适配，未逐个运行完整设计任务。同时读取 `~/.agents/skills` 和 `~/.claude/skills` 的宿主（Copilot、Cursor、OpenCode）在两处都安装时可能显示两次，只装一处即可。`--project 目录` 安装到项目级目录。

安装方式：`npx -y github:1837620622/ad-and-psim-skill install`、`npx skills add 1837620622/ad-and-psim-skill`、CC Switch（Subdirectory 填 `skills`）或 `python scripts/install_skills.py`，详见 README。安装器不安装 AD/PSIM，不改全局配置和工具权限。

## MCP

不支持技能目录、但支持 MCP 的客户端，用 MCP 服务器接入同样的功能：`npx -y github:1837620622/ad-and-psim-skill mcp`，或直接运行 `skills/ad-schematic-layout/scripts/mcp_server.py --with skills/psim-simulation-layout/scripts`。服务器支持 MCP 协议 2024-11-05 到 2025-11-25，工具参数只用基本 JSON 类型，方便各家模型调用。

服务器提供 32 个工具，包括上 Windows 前的离线预测、跨系统的任务准备、原生结果接收和一致性比较。原生调用仍在 Windows 执行；可在 Mac/Linux 上先准备任务目录，再离线传到 Windows 双击运行，不需要启动网络服务。

## 让不同模型给出一致的结果

不同模型的审美和看图能力差别很大，所以排版质量交给确定性的检查：

1. **规则写成数字**：栅格、字位、间距、比例、参数写法，见两个技能的 `references/drafting-rules.md`。
2. **程序判定**：`check` 在建模前判定通过与否，`create` 遇到 error 拒绝写文件；AD `verify` 按逐引脚拓扑判定连接；`export` 的 `text_review` 在原生图上判定文字重叠、越界和压线。
3. **结构化输出**：所有命令输出 JSON，能力弱的模型也能逐条读取、逐条修正。
4. **按需加载**：SKILL.md 很短，细节在 references 里，适合上下文较短的模型。
5. **双语描述**：frontmatter 的 description 同时有英文和中文关键词，中英文请求都能触发。

不能看图的模型也能通过前面的自动检查，但最后的看图审阅要交给能看图的模型或人。只有聊天、没有本地工具的模型不能操作 AD 或 PSIM，只能起草计划，由用户在本机运行命令。

## 手动加载 / Explicit loading

宿主没有技能目录时，把下面这段作为任务开头：

```text
Use the current repository as the skill-suite root.
For AD, read skills/ad-schematic-layout/SKILL.md and references/drafting-rules.md.
For PSIM, read skills/psim-simulation-layout/SKILL.md and references/drafting-rules.md.
Resolve references and scripts relative to the selected skill directory.
Run the check command until it reports 0 errors before any native step.
Use the native software on Windows to verify, simulate and export; fix every text_review finding.
```

## 操作系统 / Operating systems

预检、生成 AD 文件、导入修改、渲染、PSIM 构建包、波形测量和交付在 Windows、macOS、Linux 上都能运行。AD 原生脚本、PSIM 接口、原生出图和窗口截图需要 Windows 与已授权的软件；在其他系统上，把生成的 AD 文件或 PSIM 构建包交给有软件的 Windows 电脑即可。

仿原生出图按 Windows 原生导出标定；macOS 自带 Times New Roman 和 Arial，Linux 用字宽相同的 Liberation 字体（`fonts-liberation`），`env` 会显示所用字体。psimsch 是 PSIM 的私有格式，只能在 Windows 上由 PSIM 写出；PSIM 构建包最后会自动打开模型。

`handoff` / `receive` 让 Mac/Linux 不装软件也能完成整个流程：准备计划和便携预览，Windows 实际编译或求解，再接收原生 PNG 与原始结果。原生 PNG 按字节复制，因此不受 Mac/Linux 的本地字体替换影响；离线便携渲染仍是近似图。操作步骤见 [交接与比较](skills/ad-schematic-layout/references/handoff.md)。

Checks, AD file generation, import and editing, rendering, PSIM build kits, waveform measurement and delivery run on Windows, macOS and Linux. Native AD scripts, the PSIM API, native export and window screenshots need Windows with licensed software.

Handoff/reception lets Mac/Linux complete the workflow without AD/PSIM installed. Windows performs the native steps; reception verifies and copies its native PNG and raw results byte for byte. Offline portable rendering remains approximate. The portable CI matrix includes all three operating systems with Python 3.10 and 3.13; native checks are separate.

来源 / Sources：[Agent Skills](https://agentskills.io/specification)、[Codex](https://learn.chatgpt.com/docs/build-skills)、[Claude Code](https://code.claude.com/docs/en/skills)、[Claude 插件](https://code.claude.com/docs/en/plugins-reference)、[Gemini CLI](https://geminicli.com/docs/cli/skills/)、[GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)、[Cursor](https://cursor.com/docs/skills)、[OpenCode](https://opencode.ai/docs/skills)、[ZCode](https://www.zcode.network/en/docs/skill/)、[DSH](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)。
