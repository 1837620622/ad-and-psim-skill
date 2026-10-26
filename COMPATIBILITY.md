# Agent 兼容与调用 / Agent compatibility

两个技能采用 [Agent Skills 开放格式](https://agentskills.io/specification)：SKILL.md 加相对引用的参考、脚本和示例，指令是普通 Markdown，脚本以 Python 标准库为主。能否使用取决于**宿主**，而不是模型品牌：宿主须让模型读取本地文件、运行命令并查看图片。满足这三点时，Claude、GPT/Codex、Gemini、Grok、DeepSeek、Qwen、Kimi、GLM 等模型都按同一套指令工作。

Both skills follow the Agent Skills format. Compatibility depends on the host, not the model vendor: the host must let the model read local files, run commands and inspect images.

## 宿主与发现目录 / Hosts and discovery paths

`~/.agents/skills` 已成为多数宿主共同读取的用户目录，所以 `common` 入口覆盖的宿主最多。

| 宿主 / Host | 用户级目录 / User path | 安装入口 / Profile | 状态 / Status |
| --- | --- | --- | --- |
| Codex | `~/.agents/skills` | common | 实际发现已验证 / discovery checked |
| Gemini CLI | `~/.agents/skills`（或 `~/.gemini/skills`） | common | 按官方目录适配 / documented path |
| GitHub Copilot（CLI、VS Code、JetBrains、云端 Agent） | `~/.agents/skills`、`~/.copilot/skills`、`~/.claude/skills` | common | 按官方目录适配 / documented path |
| Cursor | `~/.agents/skills`、`~/.cursor/skills`、`~/.claude/skills` | common | 按官方目录适配；用户级技能仅本机生效 |
| OpenCode | `~/.agents/skills`、`~/.claude/skills`、`~/.config/opencode/skills` | common | 按官方目录适配 / documented path |
| Claude Code | `~/.claude/skills`，或仓库自带的插件清单 | claude | 目录适配 / directory adapter |
| ZCode | `~/.zcode/skills` | zcode | 目录适配 / directory adapter |
| DSH / DeepSeek Harness | 用户或项目 `.agents/skills`，另支持 `.dsh/skills` | common | 宿主需启用技能工具 |
| Grok 及其他宿主 / Others | 由宿主决定 / host-specific | 手动加载 | 见下方通用入口 |

除 Codex 外，表中状态表示目录按官方文档适配，尚未在各宿主中运行完整电路任务。同时读取 `~/.agents/skills` 与 `~/.claude/skills` 的宿主（Copilot、Cursor、OpenCode）在两个入口都安装时可能列出两次，只装宿主需要的入口即可。

安装器的 `--home` 指向某个本机项目目录时，会在该项目下创建 `.agents/skills` 等入口，供只读取项目级目录的宿主使用。

## 让不同模型给出一致结果 / Consistent results across models

不同模型的审美与看图能力差别很大，本包把排版质量交给确定性的检查，而不是交给模型的"感觉"：

1. **数字化规则。** [AD 排版硬规则](skills/ad-schematic-layout/references/drafting-rules.md)与 [PSIM 排版硬规则](skills/psim-simulation-layout/references/drafting-rules.md)把栅格、字位、间距、比例和参数写法写成具体数值。
2. **自动闸门。** `check_layout.py` 在原生建模前判定 pass/fail；AD `verify` 按逐引脚拓扑判定连接；两个 `export` 的 `text_review` 在原生 EMF 上判定文字重叠、越界与压线。`create` 遇到预检 error 直接拒绝。
3. **JSON 输出。** 所有工具输出结构化 JSON，弱模型也能逐条读取并修正，不依赖长篇推理。
4. **按需加载。** SKILL.md 控制在百行以内，细节放在 references，适合上下文较短的模型。
5. **双语描述。** frontmatter 的 description 同时含英文和中文关键词，中英文请求都能触发技能。

没有看图能力的模型仍可通过前三道检查，但最终审图须由能看图的模型或人工完成。只有聊天、没有本地工具的模型不能直接操作 AD 或 PSIM，只能起草计划，由用户在本机运行命令。

Numeric drafting rules, automatic gates and JSON reports make results depend on checks rather than model taste. Text-only models can pass the automated gates, but final visual review needs a vision-capable model or a person. Chat-only models without local tools cannot operate the software.

## 通用入口 / Explicit loading

宿主没有技能目录时，把下面的说明作为任务开头：

```text
Use the current repository as the skill-suite root.
For AD, read skills/ad-schematic-layout/SKILL.md and references/drafting-rules.md.
For PSIM, read skills/psim-simulation-layout/SKILL.md and references/drafting-rules.md.
Resolve references and scripts relative to the selected skill directory.
Run scripts/check_layout.py until it reports 0 errors before any native step.
Use local native software to build, validate and export editable circuits,
then fix every text_review finding and inspect the exported images.
```

安装器只创建两项技能的入口，不修改全局 AGENTS.md，不安装 CAD 软件，也不改变工具权限。Windows 使用目录联接，其他系统使用符号链接；不同内容的同名目录保留并报冲突。

原生 AD 脚本、PSIM DLL 与 GDI 后端需要 Windows。其他系统可以运行预检、读取指令和分析数据；需要实际控制软件时，须连接已授权的 Windows 执行宿主。本机通路成功不等于每个 Agent、系统和软件版本都已验证。

The installer adds discovery entries only. Windows native backends require an appropriately licensed Windows execution host. Directory compatibility is distinct from an end-to-end design test.

已验证的 Codex 完整名称 / Validated Codex names：

- `ad-and-psim-skill:ad-schematic-layout`
- `ad-and-psim-skill:psim-simulation-layout`

安装后重新打开会话或按宿主说明刷新技能列表，以实际发现名称为准。

来源 / Sources：[Agent Skills 规范](https://agentskills.io/specification)、[Codex](https://learn.chatgpt.com/docs/build-skills)、[Claude Code](https://code.claude.com/docs/en/skills)、[Claude 插件](https://code.claude.com/docs/en/plugins-reference)、[Gemini CLI](https://geminicli.com/docs/cli/skills/)、[GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)、[Cursor](https://cursor.com/docs/skills)、[OpenCode](https://opencode.ai/docs/skills)、[ZCode](https://www.zcode.network/en/docs/skill/)、[DSH](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)。
