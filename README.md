# AD and PSIM Skill

**简体中文** · [English](README.en.md)

让 AI 编程助手按一句话需求，做出**可编辑的 Altium Designer 原理图**和**能真实仿真的 PSIM 模型**，排版达到正式工程图的水平。支持 Claude Code、Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode 等，也可以作为 MCP 服务器接入任何支持 MCP 的客户端。

> **专有商业授权，不是开源项目。** 使用、修改和集成需要书面授权，见 [LICENSE](LICENSE)。联系微信：**1837620622（传康Kk）**。

| AD 示例（便携渲染） | PSIM 示例（便携渲染） |
| --- | --- |
| ![AD RC 示例](docs/images/ad-rc-render.png) | ![PSIM RC 示例](docs/images/psim-rc-render.png) |

两张图由本包的便携渲染器生成，不需要安装 AD 或 PSIM；原生导出与验证记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 能做什么

| | AD 原理图 | PSIM 仿真 |
| --- | --- | --- |
| 建模 | 生成 SchDoc + PrjPcb，在任何系统上字节一致 | 生成 Windows 构建包，由 PSIM 写出 psimsch |
| 改现有图 | 导入 SchDoc → 按操作清单修改 → 重新生成，连线自动正交重连 | 按操作清单修改计划，移动元件时导线自动绕开符号 |
| 排版检查 | 栅格、悬空线、隐式短路、预测网表、文字重叠与压线、穿件导线、画面密度、参数写法 | 导线、栅格、文字重叠与压线、导线穿符号、仿真控制位置、参数写法 |
| 预览 | 与 AD 原生导出几乎一致的便携渲染（PNG/SVG） | PSIM 样式的便携渲染（PNG/SVG） |
| 原生（Windows） | 编译、逐引脚网表比较、原生出图、窗口截图 | 建模、改参数、求解、波形读回、原生出图、窗口截图 |
| 结果核验 | 原生 EMF 上的文字重叠、越界、压线审查 | 同左；另有按时间加权的功率、效率、RMS、门极频率测量 |
| 交付 | 客户目录只放工程和图纸，过程文件另存归档，不打压缩包 | 客户目录只放模型和仿真结果，过程文件另存归档 |

## Windows、macOS、Linux 都能用

AD 和 PSIM 只有 Windows 版。本包把能脱离软件完成的工作都做成了纯 Python（3.10+，只用标准库）：

| 工作 | Windows | macOS / Linux |
| --- | --- | --- |
| 写计划、排版预检、便携渲染、修改计划 | ✓ | ✓ |
| AD：生成 SchDoc + PrjPcb | ✓ | ✓（文件与 Windows 上生成的完全相同） |
| PSIM：生成构建包 | ✓ | ✓（拷到装有 PSIM 的 Windows 电脑双击 `build.bat`） |
| AD 编译与出图、PSIM 建模与求解、窗口截图 | ✓（需装软件） | 交给有软件的 Windows 电脑 |
| 波形测量、整理交付 | ✓ | ✓ |

在 Mac 上做好的 AD 图纸可以直接发给客户；PSIM 的 psimsch 是私有二进制格式，所以在 Mac 上生成的是构建包，由客户或同事的 PSIM 自己写出原生文件，打开效果与在 Windows 上直接建模一致。

## 安装

先装 [Python 3.10+](https://www.python.org/downloads/)；PNG 渲染和截图转换需要 Pillow：`python -m pip install -r requirements-optional.txt`。

### 方式一：npx（推荐，需要 Node 18+）

```bash
npx -y github:1837620622/ad-and-psim-skill install            # 装到 ~/.agents/skills 和 ~/.claude/skills
npx -y github:1837620622/ad-and-psim-skill install --all      # 装到全部已知 Agent 目录
npx -y github:1837620622/ad-and-psim-skill doctor             # 检查 Python、Pillow、AD、PSIM
```

### 方式二：Skills CLI

```bash
npx skills add 1837620622/ad-and-psim-skill
```

### 方式三：CC Switch

在 CC Switch 的「Skills → 仓库管理 → 添加仓库」中填写：Owner `1837620622`，Name `ad-and-psim-skill`，Branch `main`，Subdirectory `skills`，然后安装两个技能。部分版本只识别根目录下的 SKILL.md，检测不到时改用方式一。

### 方式四：克隆后用 Python 安装

```bash
git clone https://github.com/1837620622/ad-and-psim-skill.git
cd ad-and-psim-skill
python scripts/install_skills.py                 # 默认装到 ~/.agents/skills 和 ~/.claude/skills
python scripts/install_skills.py --agent gemini --agent cursor
python scripts/install_skills.py --link          # 用链接，仓库更新后自动生效
```

安装器只替换它自己装过的目录，同名的其他目录会保留并报告冲突。`~/.agents/skills` 是 Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode 共同读取的目录；Claude Code 读 `~/.claude/skills`。各宿主的目录见 [兼容说明](COMPATIBILITY.md)。装完重新打开 Agent 会话。

## 使用

### 直接说需求

```text
用 ad-schematic-layout 按附件的任务书和参考图画一张可编辑的 DSP 最小系统原理图，
只画要求的硬件，DSP 用一个完整符号。排版预检通过后在 Windows 上编译、出图，整理交付目录。
```

```text
用 psim-simulation-layout 按给定拓扑和额定值搭一个反激变换器，功率主路在上、控制和反馈在下。
跑启动、额定和负载阶跃，核对开关频率、稳态、步长和功率平衡，交付模型和真实波形。
```

```text
导入 work/old.SchDoc，只调整排版，器件、参数和连接都不变；预检通过后生成新图并渲染给我看。
```

### 命令行

```bash
# AD：任何系统
python skills/ad-schematic-layout/scripts/native_ad.py check skills/ad-schematic-layout/assets/rc-filter-plan.json --preview work/draft.png
python skills/ad-schematic-layout/scripts/native_ad.py create skills/ad-schematic-layout/assets/rc-filter-plan.json work/ad
python skills/ad-schematic-layout/scripts/native_ad.py render work/ad/RC_Filter.SchDoc work/ad/view.png

# PSIM：任何系统生成构建包，Windows 上双击 build.bat
python skills/psim-simulation-layout/scripts/native_psim.py check skills/psim-simulation-layout/assets/rc-filter-plan.json
python skills/psim-simulation-layout/scripts/native_psim.py package skills/psim-simulation-layout/assets/rc-filter-plan.json work/psim-kit
```

全部命令见 [AD 命令](skills/ad-schematic-layout/references/commands.md) 和 [PSIM 命令](skills/psim-simulation-layout/references/commands.md)。

### MCP

MCP 服务器只用 Python 标准库，提供 23 个工具（`ad_*` 和 `psim_*`），可以读取、修改、检查、渲染当前图纸。

```bash
claude mcp add ad-psim -- npx -y github:1837620622/ad-and-psim-skill mcp    # Claude Code
```

Cursor（`~/.cursor/mcp.json`）、Gemini CLI（`~/.gemini/settings.json`）等使用 `mcpServers` 的客户端：

```json
{
  "mcpServers": {
    "ad-psim": { "command": "npx", "args": ["-y", "github:1837620622/ad-and-psim-skill", "mcp"] }
  }
}
```

Codex（`~/.codex/config.toml`）：

```toml
[mcp_servers.ad-psim]
command = "npx"
args = ["-y", "github:1837620622/ad-and-psim-skill", "mcp"]
```

不想用 Node 时，把命令换成 `python`，参数换成 `["<仓库>/skills/ad-schematic-layout/scripts/mcp_server.py", "--with", "<仓库>/skills/psim-simulation-layout/scripts"]`。

## 排版标准

"好看"被写成了具体数字，并由程序判定，不依赖模型的审美：

1. **计划预检**：栅格、连接、文字间距、比例、密度和参数写法，0 error 才能生成文件。
2. **原生连接**（AD）或**原生求解**（PSIM）。
3. **原生图面**：在原生导出的 EMF 上查文字重叠、越界和被线穿过，然后人工看图。

规则全文：[AD 排版硬规则](skills/ad-schematic-layout/references/drafting-rules.md)、[PSIM 排版硬规则](skills/psim-simulation-layout/references/drafting-rules.md)。

## 截图

`screenshot` 命令在装有软件的 Windows 上会打开 AD 或 PSIM、等文档加载完、最大化后截取真实窗口；没有软件时改用便携渲染，结果里标明 `portable_render`。便携渲染用于调试，对外的图请用原生导出或真实截图。

## 交付

```bash
python skills/ad-schematic-layout/scripts/native_ad.py deliver work/ delivery/ --name 项目名
```

得到两个目录：`delivery/项目名/` 给客户，只有工程文件、仿真结果和正式图纸；`delivery/项目名-archive/` 自己留，放计划、脚本、报告、草图和每个文件的 SHA-256 清单。不打压缩包，工作目录里的文件只复制不移动。

## 目录结构

```text
ad-and-psim-skill/
├── skills/
│   ├── ad-schematic-layout/       # AD 技能：SKILL.md、references/、scripts/、assets/
│   └── psim-simulation-layout/    # PSIM 技能：同上
├── bin/cli.mjs                    # npx 入口：install / mcp / doctor
├── scripts/install_skills.py      # Python 安装器
├── tests/                         # 可移植测试（不需要 AD、PSIM）
└── docs/                          # 验证记录和示例图
```

每个技能目录自成一体，复制到任何 Agent 的技能目录都能用。

## 验证状态

- 可移植部分（预检、生成、导入与修改、渲染、构建包、MCP、安装器）有自动测试，在 Linux 上用 Python 3.10 和 3.13 运行：`python -m unittest discover -s tests -v`。
- 原生部分在 AD Enterprise 26.4.1、PSIM 2026.0.0.7209 上验证过；记录、边界和待复验的项目见 [docs/VALIDATION.md](docs/VALIDATION.md)。
- Codex 的技能发现实际验证过；其他宿主按官方文档的目录适配，未逐个运行完整设计任务。

## 授权与联系

本项目公开源码但**不是开源软件**，没有默认的免费使用或试用许可。法律和平台条款允许的浏览、fork 不受影响；其他使用、修改、集成和再分发需要书面授权，见 [LICENSE](LICENSE)。赞助本身不产生授权。

- 微信：**1837620622（传康Kk）**，只接受赞助、商业合作和授权咨询。
- 问题反馈：[提交 Issue](https://github.com/1837620622/ad-and-psim-skill/issues/new/choose)，写清软件和 Agent 版本、复现步骤、日志；不要上传账号凭据或客户保密工程。
- 第三方产品名称只用于说明兼容对象，不表示官方关联或背书，见 [第三方声明](THIRD_PARTY_NOTICES.md)。
