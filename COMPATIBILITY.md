# Agent 兼容与调用 / Agent compatibility

两个技能采用 [Agent Skills 格式](https://agentskills.io/specification)，分别包含 SKILL.md、相对引用、脚本和参考。宿主负责加载指令、执行命令及查看输出；模型本身不提供本地软件控制接口。

Both skills use the SKILL.md structure. The host must supply local file access, command execution and image inspection.

| 工具 / Host | 发现入口 / Discovery path | 适配与验证 / Adapter and validation |
| --- | --- | --- |
| Codex | `~/.agents/skills/<name>/SKILL.md` | common；附 agents/openai.yaml；实际技能发现已验证 / discovery checked |
| Claude Code | `~/.claude/skills/<name>/SKILL.md` | claude；另附插件清单；目录适配，未完整运行设计任务 / directory adapter |
| ZCode | `~/.zcode/skills/<name>/SKILL.md` | zcode；目录适配，未完整运行设计任务 / directory adapter |
| DSH / DeepSeek Harness | 用户或项目 .agents/skills；另支持 .dsh/skills | common；宿主需启用技能工具 / host skill tool required |
| Grok / 其他 / Other | 由宿主决定 / host-specific | 手动加载 SKILL.md 与本地工具 / explicit loading and local tools |

## 通用入口 / Explicit loading

```text
Use the current repository as the skill-suite root.
For AD, read skills/ad-schematic-layout/SKILL.md.
For PSIM, read skills/psim-simulation-layout/SKILL.md.
Resolve references and scripts relative to the selected skill directory.
Use local native software to build, validate and export editable circuits.
```

安装器只创建两项技能的入口，不修改全局 AGENTS.md，不安装 CAD 软件，也不改变工具权限。Windows 使用目录联接，其他系统使用符号链接；不同内容的同名目录保留并报冲突。

原生 AD 脚本、PSIM DLL 与 GDI 后端需要 Windows。其他系统可以读取指令或分析数据；需要实际控制软件时，须连接已授权的 Windows 执行宿主。本机通路成功不等于每个 Agent、系统和软件版本都已验证。

The installer adds discovery entries only. Windows native backends require an appropriately licensed Windows execution host. Directory compatibility is distinct from an end-to-end design test.

已验证的 Codex 完整名称 / Validated Codex names：

- `ad-and-psim-skill:ad-schematic-layout`
- `ad-and-psim-skill:psim-simulation-layout`

安装后重新打开会话或按宿主说明刷新技能列表，以实际发现名称为准。

来源 / Sources：[Codex](https://developers.openai.com/codex/skills/)、[Claude Code](https://code.claude.com/docs/en/skills)、[Claude 插件](https://code.claude.com/docs/en/plugins-reference)、[ZCode](https://www.zcode.network/en/docs/skill/)、[DSH](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)。
