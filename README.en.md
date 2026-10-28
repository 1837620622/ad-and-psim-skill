# AD and PSIM Skill

[简体中文](README.md) · **English**

[Changelog](CHANGELOG.md) · [Validation](docs/VALIDATION.md)

[![License: Proprietary](https://img.shields.io/badge/license-proprietary-c0392b)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab)
![Windows | macOS | Linux](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-555555)
![Agent Skills](https://img.shields.io/badge/Agent%20Skills-2%20skills-6f42c1)
![MCP](https://img.shields.io/badge/MCP-32%20tools-0a7ea4)

Two skills for AI coding agents: turn a plain-language request into an **editable Altium Designer schematic** or a **PSIM model solved by PSIM itself**, with the layout checked rule by rule against formal drawing practice. The output is native project files, not pictures.

Use them as skills in Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, OpenCode and others, or as an MCP server in any MCP client.

> **Proprietary commercial project, not open source.** Use, modification and integration require written authorization; see [LICENSE](LICENSE). WeChat: **1837620622**.

| | AD example | PSIM example |
| --- | --- | --- |
| Windows native export | ![AD native export](docs/images/ad-native-rc.png) | ![PSIM native export](docs/images/psim-native-rc.png) |
| Mac/Linux Windows-look render (no AD/PSIM) | ![AD Windows-look render](docs/images/ad-rc-render.png) | ![PSIM Windows-look render](docs/images/psim-rc-render.png) |

The second row was produced by this package on Linux without AD or PSIM. Compared pixel by pixel with the Windows native exports in the first row, the images have the same size, and counting only lines and text (not the white background) 97.8% (AD) and 97.1% (PSIM) of the pixels line up within one pixel; the remaining differences are mostly anti-aliasing at text edges. The method is in [docs/VALIDATION.md](docs/VALIDATION.md).

## What it does

| | AD schematics | PSIM simulation |
| --- | --- | --- |
| Modeling | Writes SchDoc + PrjPcb, byte-identical on every OS | Builds a Windows kit; PSIM writes the psimsch |
| Editing existing work | Import SchDoc → apply edit operations → regenerate; wires re-route orthogonally | Edit the plan; moved elements drag their wires around symbols |
| Layout check | Grid, dangling wires, implicit shorts, predicted netlist, text overlap and text over lines, wires through parts, sheet density, value notation | Wires, grid, text overlap and text over lines, wires through symbols, simulation-control placement, value notation |
| Preview | Windows-look render (same scale, line widths and ClearType-style text); display the original native PNG returned by Windows | Windows-look render (same framing, native text placement); display the original native PNG returned by Windows |
| Before Windows | Predict compile warnings, netlist and drawing (`preflight`) | Predict text positions by the native rule; offline pre-simulation of linear circuits (`presim`) |
| Cross-OS handoff | Prepare on Mac/Linux, compile/export on Windows, verify returned files | Prepare on Mac/Linux, solve on Windows, receive native PNG/SMV/CSV |
| Native (Windows) | Compile, pin-level netlist comparison, native export, window screenshot | Create, edit parameters, solve, read back waveforms, native export, window screenshot |
| Result checks | Text overlap, clipping and text-over-line review on the native EMF | Same, plus time-weighted power, efficiency, RMS and gate-frequency measurements |
| Delivery | Customer folder holds only the project and drawings; process files go to an archive; no zip | Customer folder holds only the model and results; process files go to an archive |

## Workflow

1. **Plan**: turn the request into JSON with parts, values, coordinates and wires.
2. **Layout check** (`check`): any error stops the run until it is fixed.
3. **Offline forecast** (`preflight`): Windows-look preview, expected compile warnings, PSIM pre-simulation; go to Windows when `ready_for_windows` is true.
4. **Generate**: AD writes SchDoc + PrjPcb; PSIM gets a build kit, or a native model on Windows.
5. **Native check** (Windows): AD compiles and compares the pin-level netlist; PSIM solves and reads back waveforms.
6. **Native export**: review text overlap, clipping and text over lines, then look at the drawing.
7. **Delivery**: a customer folder plus a process archive.

Every step prints JSON, so the model reads and fixes findings one by one instead of judging "close enough" by itself.

## Requirements

| For | You need |
| --- | --- |
| Checks, generation, editing, SVG render, build kit, delivery | Python 3.10+ (standard library only) on Windows, macOS or Linux |
| PNG render | The Windows-look render needs Pillow plus Times New Roman/Arial (bundled with Windows and macOS) or the width-identical Liberation fonts (Linux: `fonts-liberation`); otherwise resvg-py or Pillow draw a smooth preview. Optional dependencies: `python -m pip install -r requirements-optional.txt` |
| Windows native EMF to PNG, screenshot conversion | Python 3.11+ and Pillow 13 (included in the optional requirements above) |
| Installing or running MCP via npx | Node.js 18+ |
| AD compile and native export | Windows + licensed Altium Designer (validated with Enterprise 26.4.1) |
| PSIM native modeling, solving and export | Windows + licensed PSIM with its Python API (validated with 2026.0.0.7209) |

Other software versions have not been validated and are not covered.

Optional requirements depend on the Python version: 3.10 gets resvg-py only (smooth previews, no Windows-look render); 3.11+ also gets Pillow 13 (Windows-look render, native EMF to PNG on Windows), so no older Pillow with known vulnerabilities is pulled in. `render` uses the Windows-look renderer by default (`--renderer gdi`); choose `--renderer resvg` or `--renderer pillow` explicitly, and point to font files with `--font-file` and `--font-dir`. See [preview backends](docs/preview-backends.md) for the comparison and font notes.

## Works on Windows, macOS and Linux

AD and PSIM run only on Windows. Everything that does not need the software is plain Python:

| Task | Windows | macOS / Linux |
| --- | --- | --- |
| Plan, layout check, plan editing | ✓ | ✓ |
| Windows-look preview, offline forecast (`preflight`), PSIM pre-simulation | ✓ | ✓ |
| AD: write SchDoc + PrjPcb | ✓ | ✓ (identical to files written on Windows) |
| PSIM: build kit | ✓ | ✓ (copy to a Windows PC with PSIM and double-click `build.bat`) |
| AD compile/export, PSIM create/solve, window screenshots | ✓ (with the software) | Hand over to a Windows PC with the software |
| Waveform measurement, delivery | ✓ | ✓ |

Mac/Linux does not need AD or PSIM: AD files can be written there directly and are compiled and exported on Windows before delivery; PSIM models and results always come from PSIM on Windows. See [Making PSIM simulation files on a Mac or a PC without PSIM](#making-psim-simulation-files-on-a-mac-or-a-pc-without-psim) and [Prepare on Mac/Linux, run on Windows](#prepare-on-maclinux-run-on-windows) under Usage.

### How the result matches what Windows shows

- **The same file**: an AD SchDoc is byte-identical whichever OS writes it.
- **The same drawing**: the Windows-look renderer is calibrated pixel by pixel against native exports: pixel scale, line widths, rounding, ClearType-style colored text edges, and PSIM's text placement rule (text start = horizontal centre of AREA - FormatFactor).
- **The same text widths**: macOS ships Times New Roman and Arial; Linux uses the Liberation fonts, whose glyph widths match exactly, so text positions and line breaks are the same as on Windows and only stroke details differ. `env` shows which fonts are in use.
- **Know the result in advance**: `preflight` predicts the compile warnings AD will report (four missing footprints for the RC example, as measured on Windows); linear PSIM circuits are pre-simulated with the same method class as PSIM (nodal analysis, fixed-step trapezoidal), within about 0.00003 V of the analytic RC solution.
- **Automatic reconciliation**: after a handoff job runs on Windows, the returned manifest records whether the predicted warning count matched and the point-by-point deviation between the pre-simulation and PSIM's waveforms.

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

# Before Windows: offline forecast (Windows-look preview, expected compile warnings, PSIM pre-simulation)
python $AD/scripts/native_ad.py preflight $AD/assets/rc-filter-plan.json work/preflight-ad
python $PSIM/scripts/native_psim.py preflight $PSIM/assets/rc-filter-plan.json work/preflight-psim
python $PSIM/scripts/native_psim.py presim $PSIM/assets/rc-filter-plan.json work/presim.csv
```

All commands: [AD commands](skills/ad-schematic-layout/references/commands.md), [PSIM commands](skills/psim-simulation-layout/references/commands.md).

### Making PSIM simulation files on a Mac or a PC without PSIM

Only PSIM itself can write a psimsch (see the [FAQ](#faq)), so the work is split: the machine without PSIM settles everything it can, and Windows needs a single double-click.

1. **Write the plan and check it**: run `check plan.json` until it reports 0 errors. When text overlaps text or wires, the `place_text` operation of `plan-edit` moves it to a free position.
2. **Forecast offline**: `preflight plan.json work/preflight` writes a Windows-look preview and pre-simulates linear circuits (`presim.csv`), so topology, values and waveform levels are checked first. Continue when `ready_for_windows` is true.
3. **Package**: `package plan.json work/psim-kit` builds the kit; use `handoff` (next section) when the results must come back verified.
4. **Double-click on Windows**: copy the folder to a Windows PC with PSIM and 64-bit Python 3.10+, then double-click `build.bat`. PSIM writes `name.psimsch`, solves it into SMV and CSV under `result\`, exports the native drawing to `drawing\` and finally opens the model.
5. **If something fails**: the window stays open with the reason, and every step is recorded in `build-report.json`. Fix the cause and double-click again. An existing psimsch is reused, so edits made in PSIM are kept; only the solve and the drawing are redone.

Without a Windows PC, a Windows virtual machine or a remote desktop to a PC with PSIM can be used. Neither has been verified with this package; whether PSIM runs and activates its license in a virtual machine is up to PSIM.

### Prepare on Mac/Linux, run on Windows

On a computer without AD or PSIM, `handoff` prepares a job folder with the plan, the tools that run it and an offline preview:

```bash
python $AD/scripts/native_ad.py handoff $AD/assets/rc-filter-plan.json work/job-ad
python $PSIM/scripts/native_psim.py handoff $PSIM/assets/rc-filter-plan.json work/job-psim --name RC_Filter
```

Copy the whole folder to a Windows PC with the licensed software (plus 64-bit Python 3.11+ and Pillow 13: `py -3 -m pip install Pillow==13.0.0`) and double-click `run.bat`. The software is found through the registry and common folders; set `AD_EXE` or `PSIM_DIR` if it is not. AD creates, compiles, compares nets and exports; PSIM creates, solves and exports. Any failed stage stops the run, the window stays open with the reason and the diagnostics stay in `native-results\`. Fix the cause and double-click again: the failed attempt is renamed to `native-results.failed-1` and so on, and a passed result is never overwritten.

Copy the resulting `native-results/` back (here as `work/returned-ad` and `work/returned-psim`) and receive it:

```bash
python $AD/scripts/native_ad.py receive work/job-ad work/returned-ad work/final-ad
python $PSIM/scripts/native_psim.py receive work/job-psim work/returned-psim work/final-psim
```

Reception checks the request, the plan and the SHA-256 of every file, and rejects mismatched plans, failed native checks and modified files. PNG, SMV and CSV are copied unchanged, never redrawn or recalculated. Add dependencies such as parameter files with `--include params.txt` when preparing the job.

The job folder also carries the offline forecast in `preflight/`. After the Windows run, the `forecast` entry of the returned manifest compares prediction and reality (AD: predicted vs actual compile warnings; PSIM: largest deviation between the pre-simulation and PSIM's waveforms).

| Picture | What it shows |
| --- | --- |
| `preview.render.png/svg` in the job folder | Offline approximation for checking the layout; fonts and uncalibrated parts may differ from the native software |
| The `png` from `receive` | The original Windows native export, byte-identical; shows the drawing as the software draws it |

### Comparing results

```bash
python $PSIM/scripts/native_psim.py compare reference/native.csv work/final-psim/waveforms/native.csv --waveforms
python $AD/scripts/native_ad.py compare reference/drawing.png work/final-ad/drawing/RC_Filter.png
```

By default every column is compared with zero tolerance, without interpolation or smoothing. Results come in four levels: `byte_identical` (same file bytes), `numeric_equal` (identical values), `within_tolerance` (within the `--atol` / `--rtol` you give) and `different`. Agreement within a tolerance is not byte identity; different software versions, model libraries and solver settings need their own checks. See [handoff and comparison](skills/ad-schematic-layout/references/handoff.md).

### MCP

The MCP server uses only the Python standard library and exposes 32 tools to read, edit, check and render drawings, forecast results before Windows, prepare jobs for Windows, receive native results and compare files or waveforms.

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
<summary>All 32 tools</summary>

| Purpose | AD | PSIM |
| --- | --- | --- |
| Environment | `ad_env` | `psim_env` |
| Layout check | `ad_check` | `psim_check` |
| Forecast before Windows | `ad_preflight` | `psim_preflight`, `psim_presim` |
| Read and edit | `ad_import`, `ad_edit` | `psim_plan_edit`, `psim_inspect`, `psim_edit` |
| Generate | `ad_create` | `psim_package`, `psim_create` |
| Preview and screenshot | `ad_render`, `ad_screenshot` | `psim_render`, `psim_screenshot` |
| Native check | `ad_verify` | `psim_simulate`, `psim_measure` |
| Native export | `ad_export` | `psim_export` |
| Delivery | `ad_deliver` | `psim_deliver` |
| Handoff and reception | `ad_handoff`, `ad_receive` | `psim_handoff`, `psim_receive` |
| Result comparison | `ad_compare` | `psim_compare` |

`ad_verify`, `ad_export`, `psim_create`, `psim_inspect`, `psim_edit`, `psim_simulate` and `psim_export` need Windows with the software; the screenshot tools fall back to the portable render without it; all other tools run on any OS.

</details>

## Layout standard

"Looks good" is written down as numbers and decided by code, not by the model's taste:

1. **Plan check**: grid, connections, text spacing, proportions, density and value notation. Files are written only with 0 errors. Overlapping text is an error; when designators or values overlap text or lines, the `place_text` edit operation moves them to a collision-free spot.
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

Yes for plans, checks, AD file generation, PSIM build kits or handoff jobs, preview renders and delivery. Compiling, solving, native export and window screenshots need a Windows PC with the software; `receive` brings the results back unchanged.

**Will an AD file made on a Mac open differently for the customer?**

No. The generator writes the same bytes on every OS; the tests pin the SHA-256 of the example file.

**Can a Mac produce a psimsch that opens with a double-click?**

No. psimsch is PSIM's closed format: only the version line at the top is plain text and the body is encoded. To build PSIM schematics from outside, Altair points to PSIM's Python API, which runs on a PC with PSIM installed. Commercial tools such as Typhoon HIL and SIMBA need PSIM to export a netlist first, and online design tools that produce PSIM models hand over a script that runs inside PSIM. On Mac/Linux this package builds a kit instead: double-click `build.bat` on a Windows PC with PSIM and PSIM writes the psimsch, solves it, exports the drawing and finally opens the model. Step by step: [Making PSIM simulation files on a Mac or a PC without PSIM](#making-psim-simulation-files-on-a-mac-or-a-pc-without-psim). AD is different: SchDoc and PrjPcb are written directly on any OS and open in AD with a double-click on Windows (or `native_ad.py open`). Cross-OS jobs use `handoff` and `run.bat` with a verifiable return manifest.

**Skills or MCP?**

Install the skills if the host supports skill directories: they carry the layout rules and the full workflow. MCP provides the tools only and suits clients without skill directories. Both can be used together.

**Which model works best?**

It depends on whether the host lets the model read files, run commands and view images, not on the model vendor. Models that cannot view images still pass the automatic checks, but the final visual review needs a model or a person that can.

**Will it change my original project?**

No. Import only reads the original drawing and edits go to a file you name; native PSIM parameter edits save a copy; delivery only copies files.

**Can I send the Windows-look render to a customer?**

Better not. It is very close to the native export but is still a prediction; send the Windows native export or the original returned by `receive`.

**Why does text on Linux look slightly different from Windows?**

Linux uses the Liberation fonts by default. Their glyph widths equal Times New Roman and Arial, so positions, line breaks and collisions are the same; only stroke details differ. If you have licensed Times New Roman and Arial files, pass them with `--font-file`.

**Can the pre-simulation replace PSIM?**

No. It supports linear elements only (R, L, C, DC and sine sources, voltage probes) to confirm values, topology and waveform magnitudes before Windows, and refuses switches, diodes and controls. Delivered waveforms must come from PSIM.

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

- The portable parts (checks, generation, import/editing, rendering, handoff/reception, comparison, offline forecast and pre-simulation, MCP and installers) have automated tests; the Windows-look renderer is compared pixel by pixel with the native exports in the repository. The CI matrix is configured for Windows, macOS and Linux with Python 3.10/3.13: `python -m unittest discover -s tests -v`. See Actions and the validation record for actual runs.
- The native parts were validated with AD Enterprise 26.4.1 and PSIM 2026.0.0.7209; records, limits and pending re-checks are in [docs/VALIDATION.md](docs/VALIDATION.md).
- Codex skill discovery was checked in practice; other hosts use the directories from their official documentation and were not each run through a full design task.

## License and contact

The source is public but this is **not open-source software**, and there is no default free-use or trial license. Viewing and forking allowed by law and platform terms are unaffected; other use, modification, integration and redistribution require written authorization under [LICENSE](LICENSE). Sponsorship alone grants no license.

- WeChat: **1837620622**, for sponsorship, commercial cooperation and licensing only.
- Problems: [open an issue](https://github.com/1837620622/ad-and-psim-skill/issues/new/choose) with software and agent versions, steps and logs. Do not upload credentials or confidential customer projects.
- Product names identify compatibility targets only and imply no affiliation or endorsement; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
