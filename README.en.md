# AD and PSIM Skill

[简体中文](README.md) · **English**

Lets an AI coding agent turn a plain-language request into an **editable Altium Designer schematic** or a **PSIM model that really simulates**, with layout at the level of a formal engineering drawing. Works with Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, OpenCode and others, and as an MCP server for any MCP client.

> **Proprietary commercial project, not open source.** Use, modification and integration require written authorization; see [LICENSE](LICENSE). WeChat: **1837620622**.

| AD example (portable render) | PSIM example (portable render) |
| --- | --- |
| ![AD RC example](docs/images/ad-rc-render.png) | ![PSIM RC example](docs/images/psim-rc-render.png) |

Both images come from this package's portable renderer, with no AD or PSIM installed. Native exports and validation records are in [docs/VALIDATION.md](docs/VALIDATION.md).

## What it does

| | AD schematics | PSIM simulation |
| --- | --- | --- |
| Modeling | Writes SchDoc + PrjPcb, byte-identical on every OS | Builds a Windows kit; PSIM writes the psimsch |
| Editing existing work | Import SchDoc → apply edit operations → regenerate; wires re-route orthogonally | Edit the plan; moved elements drag their wires around symbols |
| Layout check | Grid, dangling wires, implicit shorts, predicted netlist, text overlap and text over lines, wires through parts, sheet density, value notation | Wires, grid, text overlap and text over lines, wires through symbols, simulation-control placement, value notation |
| Preview | Portable render that closely matches the native AD export (PNG/SVG) | PSIM-style portable render (PNG/SVG) |
| Native (Windows) | Compile, pin-level netlist comparison, native export, window screenshot | Create, edit parameters, solve, read back waveforms, native export, window screenshot |
| Result checks | Text overlap, clipping and text-over-line review on the native EMF | Same, plus time-weighted power, efficiency, RMS and gate-frequency measurements |
| Delivery | Customer folder holds only the project and drawings; process files go to an archive; no zip | Customer folder holds only the model and results; process files go to an archive |

## Works on Windows, macOS and Linux

AD and PSIM run only on Windows. Everything that does not need the software is plain Python 3.10+ using only the standard library:

| Task | Windows | macOS / Linux |
| --- | --- | --- |
| Plan, layout check, portable render, plan editing | ✓ | ✓ |
| AD: write SchDoc + PrjPcb | ✓ | ✓ (identical to files written on Windows) |
| PSIM: build kit | ✓ | ✓ (copy to a Windows PC with PSIM and double-click `build.bat`) |
| AD compile/export, PSIM create/solve, window screenshots | ✓ (with the software) | Hand over to a Windows PC with the software |
| Waveform measurement, delivery | ✓ | ✓ |

AD drawings made on a Mac can go straight to the customer. A psimsch is a proprietary binary format, so on a Mac you build a kit and the customer's or colleague's PSIM writes the native file, giving the same result as modeling on Windows.

## Install

Install [Python 3.10+](https://www.python.org/downloads/) first. PNG rendering and screenshot conversion need Pillow: `python -m pip install -r requirements-optional.txt`.

### Option 1: npx (recommended, Node 18+)

```bash
npx -y github:1837620622/ad-and-psim-skill install            # into ~/.agents/skills and ~/.claude/skills
npx -y github:1837620622/ad-and-psim-skill install --all      # into every known agent directory
npx -y github:1837620622/ad-and-psim-skill doctor             # check Python, Pillow, AD, PSIM
```

### Option 2: Skills CLI

```bash
npx skills add 1837620622/ad-and-psim-skill
```

### Option 3: CC Switch

In CC Switch, open Skills → Repository management → Add repository and enter Owner `1837620622`, Name `ad-and-psim-skill`, Branch `main`, Subdirectory `skills`, then install both skills. Some versions only detect a SKILL.md at the repository root; use option 1 if nothing is found.

### Option 4: clone and install with Python

```bash
git clone https://github.com/1837620622/ad-and-psim-skill.git
cd ad-and-psim-skill
python scripts/install_skills.py                 # default: ~/.agents/skills and ~/.claude/skills
python scripts/install_skills.py --agent gemini --agent cursor
python scripts/install_skills.py --link          # links follow repository updates
```

The installers replace only directories they installed; other directories with the same name are kept and reported. `~/.agents/skills` is read by Codex, Gemini CLI, GitHub Copilot, Cursor and OpenCode; Claude Code reads `~/.claude/skills`. See [COMPATIBILITY.md](COMPATIBILITY.md) for every host. Reopen the agent session afterwards.

## Usage

### Ask in plain language

```text
Use ad-schematic-layout to draw an editable DSP minimum-system schematic from the attached
specification and reference. Include only the required hardware and one complete DSP symbol.
After the layout check passes, compile and export on Windows and prepare the delivery folders.
```

```text
Use psim-simulation-layout to build a flyback converter with the given topology and ratings,
power stage on top, control and feedback below. Run startup, rated load and a load step; check
switching frequency, steady state, time step and power balance; deliver the model and real waveforms.
```

```text
Import work/old.SchDoc and change only the layout, keeping parts, values and connections.
After the check passes, generate the new drawing and show me a render.
```

### Command line

```bash
# AD, any OS
python skills/ad-schematic-layout/scripts/native_ad.py check skills/ad-schematic-layout/assets/rc-filter-plan.json --preview work/draft.png
python skills/ad-schematic-layout/scripts/native_ad.py create skills/ad-schematic-layout/assets/rc-filter-plan.json work/ad
python skills/ad-schematic-layout/scripts/native_ad.py render work/ad/RC_Filter.SchDoc work/ad/view.png

# PSIM: build the kit anywhere, double-click build.bat on Windows
python skills/psim-simulation-layout/scripts/native_psim.py check skills/psim-simulation-layout/assets/rc-filter-plan.json
python skills/psim-simulation-layout/scripts/native_psim.py package skills/psim-simulation-layout/assets/rc-filter-plan.json work/psim-kit
```

All commands: [AD commands](skills/ad-schematic-layout/references/commands.md), [PSIM commands](skills/psim-simulation-layout/references/commands.md).

### MCP

The MCP server uses only the Python standard library and exposes 23 tools (`ad_*` and `psim_*`) to read, edit, check and render the current drawing.

```bash
claude mcp add ad-psim -- npx -y github:1837620622/ad-and-psim-skill mcp    # Claude Code
```

Clients that use `mcpServers`, such as Cursor (`~/.cursor/mcp.json`) and Gemini CLI (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "ad-psim": { "command": "npx", "args": ["-y", "github:1837620622/ad-and-psim-skill", "mcp"] }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.ad-psim]
command = "npx"
args = ["-y", "github:1837620622/ad-and-psim-skill", "mcp"]
```

Without Node, use `python` as the command with `["<repo>/skills/ad-schematic-layout/scripts/mcp_server.py", "--with", "<repo>/skills/psim-simulation-layout/scripts"]` as arguments.

## Layout standard

"Looks good" is written down as numbers and decided by code, not by the model's taste:

1. **Plan check**: grid, connections, text spacing, proportions, density and value notation. Files are written only with 0 errors.
2. **Native connectivity** (AD) or **native solve** (PSIM).
3. **Native drawing**: text overlap, clipping and text crossed by lines on the native EMF, then a visual review.

Full rules: [AD drafting rules](skills/ad-schematic-layout/references/drafting-rules.md), [PSIM drafting rules](skills/psim-simulation-layout/references/drafting-rules.md) (in Chinese).

## Screenshots

On Windows with the software installed, `screenshot` opens AD or PSIM, waits for the document, maximizes the window and captures it. Without the software it falls back to the portable render and labels the result `portable_render`. Renders are for debugging; use native exports or real screenshots for anything you hand out.

## Delivery

```bash
python skills/ad-schematic-layout/scripts/native_ad.py deliver work/ delivery/ --name ProjectName
```

This creates `delivery/ProjectName/` for the customer, containing only project files, simulation results and final drawings, and `delivery/ProjectName-archive/` for you, with plans, scripts, reports, drafts and a SHA-256 manifest. No zip is produced, and files in the work folder are copied, never moved.

## Layout of the repository

```text
ad-and-psim-skill/
├── skills/
│   ├── ad-schematic-layout/       # AD skill: SKILL.md, references/, scripts/, assets/
│   └── psim-simulation-layout/    # PSIM skill: same structure
├── bin/cli.mjs                    # npx entry: install / mcp / doctor
├── scripts/install_skills.py      # Python installer
├── tests/                         # portable tests (no AD or PSIM needed)
└── docs/                          # validation record and example images
```

Each skill directory is self-contained and works when copied into any agent's skill directory.

## Validation

- The portable parts (checks, generation, import and editing, rendering, build kit, MCP, installers) have automated tests run on Linux with Python 3.10 and 3.13: `python -m unittest discover -s tests -v`.
- The native parts were validated with AD Enterprise 26.4.1 and PSIM 2026.0.0.7209; records, limits and pending re-checks are in [docs/VALIDATION.md](docs/VALIDATION.md).
- Codex skill discovery was checked in practice; other hosts use the directories from their official documentation and were not each run through a full design task.

## License and contact

The source is public but this is **not open-source software**, and there is no default free-use or trial license. Viewing and forking allowed by law and platform terms are unaffected; other use, modification, integration and redistribution require written authorization under [LICENSE](LICENSE). Sponsorship alone grants no license.

- WeChat: **1837620622**, for sponsorship, commercial cooperation and licensing only.
- Problems: [open an issue](https://github.com/1837620622/ad-and-psim-skill/issues/new/choose) with software and agent versions, steps and logs. Do not upload credentials or confidential customer projects.
- Product names identify compatibility targets only and imply no affiliation or endorsement; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
