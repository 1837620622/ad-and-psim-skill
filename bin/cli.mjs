#!/usr/bin/env node
// AD and PSIM Skill 的 npx 入口：安装技能、启动 MCP 服务器、检查运行环境。只用 Node 内置模块。
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SKILLS = ['ad-schematic-layout', 'psim-simulation-layout'];
const MARKER = '.installed-by-ad-and-psim-skill';
// 名称: [用户级目录, 项目级目录]，与 scripts/install_skills.py 保持一致。
const AGENTS = {
  universal: ['.agents/skills', '.agents/skills'],
  claude: ['.claude/skills', '.claude/skills'],
  codex: ['.agents/skills', '.agents/skills'],
  gemini: ['.gemini/skills', '.gemini/skills'],
  copilot: ['.copilot/skills', '.github/skills'],
  cursor: ['.cursor/skills', '.cursor/skills'],
  opencode: ['.config/opencode/skills', '.opencode/skills'],
  zcode: ['.zcode/skills', '.zcode/skills'],
};
const DEFAULT_AGENTS = ['universal', 'claude'];

const REPO = 'github:1837620622/ad-and-psim-skill';
const NPX = `npx -y ${REPO}`;
const NATIVE = [
  ['ad', 'ad-schematic-layout/scripts/native_ad.py'],
  ['psim', 'psim-simulation-layout/scripts/native_psim.py'],
];
const HOSTS = {
  universal: 'Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode',
  claude: 'Claude Code',
  codex: 'Codex',
  gemini: 'Gemini CLI',
  copilot: 'GitHub Copilot',
  cursor: 'Cursor',
  opencode: 'OpenCode',
  zcode: 'ZCode',
};

const HELP = `用法 / Usage:
  ${NPX}             一条命令：装好技能，检查并补齐 Python 依赖，检查 AD 与 PSIM
  ${NPX} install     只安装技能（JSON 输出）[--agent <名称>]... [--all] [--project <目录>] [--link]
  ${NPX} uninstall   只删除本安装器装过的目录 [--agent <名称>]... [--all] [--project <目录>]
  ${NPX} check       检查已安装的技能是否为最新
  ${NPX} doctor      检查 Python、Pillow、AD 与 PSIM（JSON 输出）
  ${NPX} mcp         启动 MCP 服务器（stdio，AD 与 PSIM 工具）[--ad-only | --psim-only]

一条命令安装的选项：--agent、--all、--project 同 install；--no-pillow 不自动安装 Pillow；--json 输出 JSON。

Agent: ${Object.keys(AGENTS).join(', ')}；默认 ${DEFAULT_AGENTS.join(' + ')}（一条命令安装时，存在 ~/.zcode 则加 zcode）
  universal = ~/.agents/skills（Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode 共用）
  claude    = ~/.claude/skills（Claude Code）`;

function parse(argv) {
  const options = { agents: [], all: false, project: null, link: false, home: os.homedir(), json: false, pillow: true };
  const rest = [];
  for (let i = 0; i < argv.length; i += 1) {
    const value = argv[i];
    if (value === '--agent') options.agents.push(argv[(i += 1)]);
    else if (value === '--all') options.all = true;
    else if (value === '--project') options.project = path.resolve(argv[(i += 1)]);
    else if (value === '--link') options.link = true;
    else if (value === '--home') options.home = path.resolve(argv[(i += 1)]);
    else if (value === '--json') options.json = true;
    else if (value === '--no-pillow') options.pillow = false;
    else rest.push(value);
  }
  for (const agent of options.agents) {
    if (!(agent in AGENTS)) throw new Error(`未知 Agent：${agent}`);
  }
  return { options, rest };
}

function targets(options) {
  const agents = options.all ? Object.keys(AGENTS) : options.agents.length ? options.agents : DEFAULT_AGENTS;
  const base = options.project ?? options.home;
  const groups = new Map();
  for (const agent of agents) {
    const dir = path.join(base, AGENTS[agent][options.project ? 1 : 0]);
    groups.set(dir, [...(groups.get(dir) ?? []), agent]);
  }
  return groups;
}

function isOurs(target, source) {
  const stat = fs.lstatSync(target);
  if (stat.isSymbolicLink()) return fs.realpathSync(target) === fs.realpathSync(source);
  return fs.existsSync(path.join(target, MARKER));
}

function exists(target) {
  try {
    fs.lstatSync(target);
    return true;
  } catch {
    return false;
  }
}

function remove(target) {
  if (fs.lstatSync(target).isSymbolicLink()) fs.unlinkSync(target);
  else fs.rmSync(target, { recursive: true, force: true });
}

function excluded(relative) {
  const parts = relative.split(path.sep);
  return parts.includes('__pycache__') || relative.endsWith('.pyc') || parts.at(-1) === MARKER
    || (parts[0] === 'references' && ['images', 'professional'].includes(parts[1]));
}

function skillFiles(root, directory = root, result = new Map()) {
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name);
    const relative = path.relative(root, file);
    if (excluded(relative)) continue;
    if (item.isDirectory()) skillFiles(root, file, result);
    else if (item.isFile()) result.set(relative, fs.readFileSync(file));
  }
  return result;
}

function sameSkill(source, target) {
  const expected = skillFiles(source);
  const actual = skillFiles(target);
  return expected.size === actual.size && [...expected].every(([name, bytes]) => actual.get(name)?.equals(bytes));
}

function applySkills(action, options) {
  const results = [];
  for (const [dir, agents] of targets(options)) {
    for (const name of SKILLS) {
      const source = path.join(ROOT, 'skills', name);
      const target = path.join(dir, name);
      const record = { entry: target, agents };
      try {
        const present = exists(target);
        if (action === 'uninstall') {
          if (present && isOurs(target, source)) {
            remove(target);
            record.status = 'removed';
          } else record.status = 'not installed by this tool';
        } else if (action === 'check') {
          if (!present) throw new Error('未安装');
          const same = sameSkill(source, target);
          if (!same) throw new Error('已安装版本与当前包不同，重新运行 install 即可更新');
          record.status = 'ok';
        } else {
          if (present) {
            if (!isOurs(target, source)) throw new Error('同名目录不是本安装器创建的，已保留');
            remove(target);
          }
          fs.mkdirSync(dir, { recursive: true });
          if (options.link) {
            fs.symlinkSync(source, target, process.platform === 'win32' ? 'junction' : 'dir');
          } else {
            fs.cpSync(source, target, {
              recursive: true,
              filter: (item) => !excluded(path.relative(source, item)),
            });
            fs.writeFileSync(path.join(target, MARKER), `${ROOT}\n`);
          }
          record.status = 'installed';
        }
        record.passed = true;
      } catch (error) {
        record.passed = false;
        record.error = error.message;
      }
      results.push(record);
    }
  }
  return { passed: results.every((r) => r.passed), entries: results };
}

function runSkills(action, options) {
  const { passed, entries } = applySkills(action, options);
  console.log(JSON.stringify({ passed, entries, next: '重新打开 Agent 会话，或按宿主说明刷新技能列表' }, null, 2));
  return passed ? 0 : 1;
}

// Python 子进程统一用 UTF-8 输出，Windows 中文系统上也能正确解析。
const PYTHON_ENV = { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' };
const PROBE = [
  'import json, sys',
  'try:',
  '    import PIL',
  '    pillow = PIL.__version__',
  'except Exception:',
  '    pillow = None',
  "print(json.dumps({'version': '%d.%d.%d' % sys.version_info[:3], 'pillow': pillow,",
  "                  'venv': sys.prefix != sys.base_prefix, 'executable': sys.executable}))",
].join('\n');

function python(command, prefix, args, extra = {}) {
  return spawnSync(command, [...prefix, ...args], { encoding: 'utf8', env: PYTHON_ENV, ...extra });
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  for (const [command, prefix] of candidates) {
    const probe = python(command, prefix, ['-c', 'import sys; print(sys.version_info >= (3, 10))']);
    if (probe.status === 0 && probe.stdout.trim() === 'True') return [command, prefix];
  }
  return null;
}

function requirePython() {
  const found = findPython();
  if (!found) {
    console.error(JSON.stringify({ error: '需要 Python 3.10 或更高版本，并加入 PATH' }));
    process.exit(1);
  }
  return found;
}

function pythonInfo([command, prefix]) {
  try {
    return JSON.parse(python(command, prefix, ['-c', PROBE]).stdout);
  } catch {
    return null;
  }
}

function nativeEnv([command, prefix]) {
  const report = {};
  for (const [key, script] of NATIVE) {
    const run = python(command, prefix, [path.join(ROOT, 'skills', script), 'env']);
    try {
      report[key] = JSON.parse(run.stdout);
    } catch {
      report[key] = { error: (run.stderr || run.stdout || '').trim() };
    }
  }
  return report;
}

function mcp(rest) {
  const [command, prefix] = requirePython();
  const ad = path.join(ROOT, 'skills', 'ad-schematic-layout', 'scripts');
  const psim = path.join(ROOT, 'skills', 'psim-simulation-layout', 'scripts');
  let args;
  if (rest.includes('--psim-only')) args = [path.join(psim, 'mcp_server.py')];
  else if (rest.includes('--ad-only')) args = [path.join(ad, 'mcp_server.py')];
  else args = [path.join(ad, 'mcp_server.py'), '--with', psim];
  const child = spawn(command, [...prefix, ...args], { stdio: 'inherit' });
  child.on('exit', (code) => process.exit(code ?? 0));
}

function doctor() {
  const found = findPython();
  const report = { node: process.version, platform: `${process.platform} ${os.release()}`, python: null };
  if (found) {
    const [command, prefix] = found;
    const version = python(command, prefix, ['--version']);
    report.python = `${command} ${(version.stdout || version.stderr).trim()}`;
    Object.assign(report, nativeEnv(found));
  } else report.python = '未找到 Python 3.10+';
  console.log(JSON.stringify(report, null, 2));
  return found ? 0 : 1;
}

function pillowRequirement() {
  const text = fs.readFileSync(path.join(ROOT, 'requirements-optional.txt'), 'utf8');
  const line = text.split(/\r?\n/).find((item) => /^pillow\b/i.test(item.trim()));
  return line ? line.split(';')[0].trim() : 'Pillow';
}

function newer(version, major, minor) {
  const [a = 0, b = 0] = String(version).split('.').map(Number);
  return a > major || (a === major && b >= minor);
}

// Pillow 是可选依赖：便携 PNG 草图、仿原生出图和波形 PNG 用它，没有时改写 SVG。
function ensurePillow(found, info, wanted) {
  const [command, prefix] = found;
  const requirement = pillowRequirement();
  const manual = [command, ...prefix, '-m', 'pip', 'install', requirement].join(' ');
  if (info.pillow) return { status: 'present', version: info.pillow };
  if (!newer(info.version, 3, 11)) {
    return { status: 'skipped', hint: `${requirement} 需要 Python 3.11+；当前 ${info.version} 的草图和波形图改写 SVG` };
  }
  if (!wanted) return { status: 'skipped', hint: `需要时运行：${manual}` };
  const args = ['-m', 'pip', 'install', '--disable-pip-version-check', '--quiet'];
  if (!info.venv) args.push('--user');
  const run = python(command, prefix, [...args, requirement], { timeout: 600000 });
  const after = run.status === 0 ? pythonInfo(found) : null;
  if (after?.pillow) return { status: 'installed', version: after.pillow };
  const output = `${run.stderr || ''}${run.stdout || ''}${run.error ? run.error.message : ''}`;
  let hint = `可以稍后手动运行：${manual}`;
  if (output.includes('externally-managed-environment')) {
    hint = '这个 Python 由系统包管理器管理，不允许 pip 直接安装。可以建虚拟环境后再运行本命令，'
      + '或用系统包（Debian/Ubuntu：sudo apt install python3-pil；macOS：brew install pillow）';
  } else if (output.includes('No module named pip')) {
    hint = `这个 Python 没有 pip：先运行 ${[command, ...prefix].join(' ')} -m ensurepip --upgrade，再运行一次本命令`;
  }
  const lines = output.trim().split(/\r?\n/).filter(Boolean);
  return { status: 'failed', error: lines.at(-1) ?? '未知错误', hint };
}

function setupAgents(options) {
  if (options.all || options.agents.length || options.project) return options;
  const agents = [...DEFAULT_AGENTS];
  if (exists(path.join(options.home, '.zcode'))) agents.push('zcode');
  return { ...options, agents };
}

const COLOR = process.stdout.isTTY && !process.env.NO_COLOR;
const paint = (code, text) => (COLOR ? `\x1b[${code}m${text}\x1b[0m` : text);
const mark = { ok: paint(32, '√'), warn: paint(33, '!'), bad: paint(31, '×') };

function pythonGuide() {
  return [
    '    Windows：winget install Python.Python.3.13，或到 https://www.python.org/downloads/ 下载，安装时勾选“Add python.exe to PATH”',
    '    macOS：brew install python，或到 https://www.python.org/downloads/ 下载',
    '    Linux：sudo apt install python3（Debian/Ubuntu），或 sudo dnf install python3（Fedora）',
    '    装好后重新打开终端，再运行一次：',
    `      ${NPX}`,
  ];
}

function setup(options) {
  const say = (line = '') => {
    if (!options.json) console.log(line);
  };
  const home = (file) => (file.startsWith(options.home) ? `~${file.slice(options.home.length)}` : file);
  const report = { passed: false };

  say('AD and PSIM Skill 安装');
  say();
  say('1/3 安装技能');
  const skills = applySkills('install', setupAgents(options));
  report.skills = skills;
  const folders = new Map();
  for (const entry of skills.entries) {
    const dir = path.dirname(entry.entry);
    folders.set(dir, [...(folders.get(dir) ?? []), entry]);
  }
  for (const [dir, entries] of folders) {
    const hosts = [...new Set(entries[0].agents.map((agent) => HOSTS[agent]))].join('、');
    const failed = entries.filter((entry) => !entry.passed);
    if (!failed.length) say(`  ${mark.ok} ${home(dir)}（${hosts}）`);
    for (const entry of failed) say(`  ${mark.bad} ${home(entry.entry)}：${entry.error}`);
  }

  say();
  say('2/3 检查 Python 与 Pillow');
  const found = findPython();
  const info = found ? pythonInfo(found) : null;
  report.python = info;
  if (!info) {
    say(`  ${mark.bad} 没有找到 Python 3.10 或更高版本。技能已装好，但检查、出图和仿真脚本都要用 Python：`);
    for (const line of pythonGuide()) say(line);
  } else {
    say(`  ${mark.ok} Python ${info.version}（${found[0]}${found[1].length ? ` ${found[1].join(' ')}` : ''}）`);
    if (!info.pillow && options.pillow && newer(info.version, 3, 11)) {
      say(`    正在安装 ${pillowRequirement()}（可选依赖，用于 PNG 出图和波形图）…`);
    }
    const pillow = ensurePillow(found, info, options.pillow);
    report.pillow = pillow;
    if (pillow.status === 'present') say(`  ${mark.ok} Pillow ${pillow.version}`);
    else if (pillow.status === 'installed') say(`  ${mark.ok} Pillow ${pillow.version}（刚刚安装）`);
    else {
      say(`  ${mark.warn} 没有 Pillow：草图和波形图改写 SVG，其他功能不受影响`);
      if (pillow.error) say(`    安装失败：${pillow.error}`);
      say(`    ${pillow.hint}`);
    }
    if (process.platform === 'win32' && !newer(info.version, 3, 11)) {
      say(`  ${mark.warn} Windows 上运行 AD、PSIM 原生步骤需要 Python 3.11+`);
    }
  }

  say();
  say('3/3 检查 Altium Designer 与 PSIM');
  if (!found) say(`  ${mark.warn} 装好 Python 后再检查`);
  else {
    const native = nativeEnv(found);
    Object.assign(report, native);
    const look = native.ad.native_look ?? native.psim.native_look;
    if (look?.available) say(`  ${mark.ok} 仿原生出图字体：${look.fonts.serif} / ${look.fonts.sans}`);
    else if (look) say(`  ${mark.warn} 仿原生出图暂不可用：${look.hint}`);
    if (native.ad.error) say(`  ${mark.bad} AD 工具自检失败：${native.ad.error}`);
    else if (native.ad.ad_exe) say(`  ${mark.ok} Altium Designer：${native.ad.ad_exe}`);
    else {
      say(`  ${mark.warn} 本机没有 Altium Designer：可以排版检查、生成和修改原理图文件、出图；`);
      say('    编译和原生导出在装有 AD 的 Windows 上完成（交接包双击 run.bat）');
    }
    if (native.psim.error) say(`  ${mark.bad} PSIM 工具自检失败：${native.psim.error}`);
    else if (native.psim.psim_dir) say(`  ${mark.ok} PSIM：${native.psim.psim_dir}`);
    else {
      say(`  ${mark.warn} 本机没有 PSIM：可以排版检查、出图、离线预仿真和生成建模包；`);
      say('    .psimsch 模型和原生仿真在装有 PSIM 的 Windows 上完成（建模包双击 build.bat）');
    }
  }

  report.passed = skills.passed && Boolean(info);
  say();
  if (report.passed) {
    say(paint(32, '安装完成。'));
    say('下一步：');
    say('  1. 重新打开 Claude Code、Codex 等 Agent（或开一个新会话），技能才会出现。');
    say('  2. 直接说需求，例如：');
    say('       用 AD 画一个 RC 低通滤波器原理图，按参考图排版');
    say('       用 PSIM 搭一个 Buck 电路并仿真，给我波形曲线和 Excel 表');
    say('  3. 可选：在 Claude Code 里接入 MCP 工具（修改电路图、排版、改文字）：');
    say(`       claude mcp add ad-psim -- ${NPX} mcp`);
    say(`更新：再运行一次 ${NPX}；卸载：${NPX} uninstall`);
  } else {
    say(paint(31, '安装没有全部完成，按上面的提示处理后再运行一次即可。'));
  }
  if (options.json) console.log(JSON.stringify(report, null, 2));
  return report.passed ? 0 : 1;
}

function main() {
  const argv = process.argv.slice(2);
  const command = argv[0] && !argv[0].startsWith('-') ? argv.shift() : 'setup';
  try {
    if (command === 'help' || argv.includes('--help') || argv.includes('-h')) {
      console.log(HELP);
      return 0;
    }
    const { options, rest } = parse(argv);
    if (command === 'setup') return setup(options);
    if (command === 'install' || command === 'uninstall' || command === 'check') return runSkills(command, options);
    if (command === 'mcp') return mcp(rest);
    if (command === 'doctor') return doctor();
    console.log(HELP);
    return 1;
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    return 1;
  }
}

const code = main();
if (typeof code === 'number') process.exitCode = code;
