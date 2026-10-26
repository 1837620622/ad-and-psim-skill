# AD and PSIM Skill

[简体中文](README.md) · **English**

[![License: Proprietary](https://img.shields.io/badge/license-proprietary-c0392b)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab)
![Windows | macOS | Linux](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-555555)
![Agent Skills](https://img.shields.io/badge/Agent%20Skills-2%20skills-6f42c1)
![MCP](https://img.shields.io/badge/MCP-23%20tools-0a7ea4)

Two skills for AI coding agents: turn a plain-language request into an **editable Altium Designer schematic** or a **PSIM model solved by PSIM itself**, with the layout checked rule by rule against formal drawing practice. The output is native project files, not pictures.

Use them as skills in Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, OpenCode and others, or as an MCP server in any MCP client.

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
| Preview | Portable render close to the native AD export (PNG/SVG) | PSIM-style portable render (PNG/SVG) |
| Native (Windows) | Compile, pin-level netlist comparison, native export, window screenshot | Create, edit parameters, solve, read back waveforms, native export, window screenshot |
| Result checks | Text overlap, clipping and text-over-line review on the native EMF | Same, plus time-weighted power, efficiency, RMS and gate-frequency measurements |
| Delivery | Customer folder holds only the project and drawings; process files go to an archive; no zip | Customer folder holds only the model and results; process files go to an archive |

## Workflow

1. **Plan**: turn the request into JSON with parts, values, coordinates and wires.
2. **Layout check** (`check`): any error stops the run until it is fixed.
3. **Generate**: AD writes SchDoc + PrjPcb; PSIM gets a build kit, or a native model on Windows.
4. **Native check** (Windows): AD compiles and compares the pin-level netlist; PSIM solves and reads back waveforms.
5. **Native export**: review text overlap, clipping and text over lines, then look at the drawing.
6. **Delivery**: a customer folder plus a process archive.

Every step prints JSON, so the model reads and fixes findings one by one instead of judging "close enough" by itself.

## Requirements

| For | You need |
| --- | --- |
| Checks, generation, editing, SVG render, build kit, delivery | Python 3.10+ (standard library only) on Windows, macOS or Linux |
| PNG render, screenshot conversion | Pillow: `python -m pip install -r requirements-optional.txt` |
| Installing or running MCP via npx | Node.js 18+ |
| AD compile and native export | Windows + licensed Altium Designer (validated with Enterprise 26.4.1) |
| PSIM native modeling, solving and export | Windows + licensed PSIM with its Python API (validated with 2026.0.0.7209) |

Other software versions have not been validated and are not covered.

## Works on Windows, macOS and Linux

AD and PSIM run only on Windows. Everything that does not need the software is plain Python:

| Task | Windows | macOS / Linux |
| --- | --- | --- |
| Plan, layout check, portable render, plan editing | ✓ | ✓ |
| AD: write SchDoc + PrjPcb | ✓ | ✓ (identical to files written on Windows) |
| PSIM: build kit | ✓ | ✓ (copy to a Windows PC with PSIM and double-click `build.bat`) |
| AD compile/export, PSIM create/solve, window screenshots | ✓ (with the software) | Hand over to a Windows PC with the software |
| Waveform measurement, delivery | ✓ | ✓ |

AD drawings made on a Mac can go straight to the customer. A psimsch is a proprietary binary format, so on a Mac you build a kit: on a Windows PC with PSIM, double-click `build.bat` and PSIM writes the native file, solves it and exports the drawing, giving the same result as modeling on Windows.

## Install

### Option 1: npx (recommended)

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

### Check, update and uninstall

```bash
npx -y github:1837620622/ad-and-psim-skill check        # is the installed copy current?
npx -y github:1837620622/ad-and-psim-skill install      # update: install again over the old copy
npx -y github:1837620622/ad-and-psim-skill uninstall    # removes only directories the installer created
```

The Python installer has `--check` and `--uninstall`; with `--link`, a `git pull` is enough to update.

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

The more precisely the request names parts, values, reference drawings and deliverables, the closer the result.

### Command line

Run from the repository root (in Windows PowerShell write the variables as `$AD = "..."` and use `$AD`):

```bash
# AD, any OS
AD=skills/ad-schematic-layout
python $AD/scripts/native_ad.py check  $AD/assets/rc-filter-plan.json --preview work/draft.png
python $AD/scripts/native_ad.py create $AD/assets/rc-filter-plan.json work/ad
python $AD/scripts/native_ad.py render work/ad/RC_Filter.SchDoc work/ad/view.png

# PSIM: build the kit anywhere, double-click build.bat on Windows
PSIM=skills/psim-simulation-layout
python $PSIM/scripts/native_psim.py check   $PSIM/assets/rc-filter-plan.json
python $PSIM/scripts/native_psim.py package $PSIM/assets/rc-filter-plan.json work/psim-kit
```

All commands: [AD commands](skills/ad-schematic-layout/references/commands.md), [PSIM commands](skills/psim-simulation-layout/references/commands.md).

### MCP

The MCP server uses only the Python standard library and exposes 23 tools to read, edit, check and render the current drawing.

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

<details>
<summary>All 23 tools</summary>

| Purpose | AD | PSIM |
| --- | --- | --- |
| Environment | `ad_env` | `psim_env` |
| Layout check | `ad_check` | `psim_check` |
| Read and edit | `ad_import`, `ad_edit` | `psim_plan_edit`, `psim_inspect`, `psim_edit` |
| Generate | `ad_create` | `psim_package`, `psim_create` |
| Preview and screenshot | `ad_render`, `ad_screenshot` | `psim_render`, `psim_screenshot` |
| Native check | `ad_verify` | `psim_simulate`, `psim_measure` |
| Native export | `ad_export` | `psim_export` |
| Delivery | `ad_deliver` | `psim_deliver` |

`ad_verify`, `ad_export`, `psim_create`, `psim_inspect`, `psim_edit`, `psim_simulate` and `psim_export` need Windows with the software; the screenshot tools fall back to the portable render without it; all other tools run on any OS.

</details>

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
python $AD/scripts/native_ad.py deliver work/ delivery/ --name ProjectName        # AD
python $PSIM/scripts/native_psim.py deliver work/ delivery/ --name ProjectName    # PSIM
```

This creates two folders:

- `delivery/ProjectName/`: for the customer, with only project files, simulation results and final drawings.
- `delivery/ProjectName-archive/`: for you, with plans, scripts, reports, drafts and a SHA-256 manifest.

No zip is produced; files in the work folder are copied, never moved.

## FAQ

**Can I use it without Windows?**

Yes for plans, checks, AD file generation, PSIM build kits, preview renders and delivery. Compiling, solving, native export and window screenshots need a Windows PC with the software.

**Will an AD file made on a Mac open differently for the customer?**

No. The generator writes the same bytes on every OS; the tests pin the SHA-256 of the example file.

**Why does PSIM need a build kit?**

A psimsch is a proprietary binary format, and only a file written by PSIM itself is sure to open the same in any PSIM. The kit holds the plan, scripts and `build.bat`; double-clicking it lets the local PSIM create, solve and export the model.

**Skills or MCP?**

Install the skills if the host supports skill directories: they carry the layout rules and the full workflow. MCP provides the tools only and suits clients without skill directories. Both can be used together.

**Which model works best?**

It depends on whether the host lets the model read files, run commands and view images, not on the model vendor. Models that cannot view images still pass the automatic checks, but the final visual review needs a model or a person that can.

**Will it change my original project?**

No. Import only reads the original drawing and edits go to a file you name; native PSIM parameter edits save a copy; delivery only copies files.

**Can I send the portable render to a customer?**

Better not. It is an approximation for debugging; send native exports or real screenshots.

## Layout of the repository

```text
ad-and-psim-skill/
├── skills/
│   ├── ad-schematic-layout/       # AD skill: SKILL.md, references/, scripts/, assets/
│   └── psim-simulation-layout/    # PSIM skill: same structure
├── bin/cli.mjs                    # npx entry: install / uninstall / check / mcp / doctor
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
