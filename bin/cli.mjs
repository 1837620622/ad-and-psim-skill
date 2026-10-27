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

const HELP = `用法 / Usage:
  npx github:1837620622/ad-and-psim-skill install [--agent <名称>]... [--all] [--project <目录>] [--link]
  npx github:1837620622/ad-and-psim-skill uninstall [--agent <名称>]... [--all] [--project <目录>]
  npx github:1837620622/ad-and-psim-skill check     检查已安装的技能是否为最新
  npx github:1837620622/ad-and-psim-skill mcp       启动 MCP 服务器（stdio，AD 与 PSIM 工具）
  npx github:1837620622/ad-and-psim-skill doctor    检查 Python、Pillow、AD 与 PSIM

Agent: ${Object.keys(AGENTS).join(', ')}；默认 ${DEFAULT_AGENTS.join(' + ')}
  universal = ~/.agents/skills（Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode 共用）
  claude    = ~/.claude/skills（Claude Code）`;

function parse(argv) {
  const options = { agents: [], all: false, project: null, link: false, home: os.homedir() };
  const rest = [];
  for (let i = 0; i < argv.length; i += 1) {
    const value = argv[i];
    if (value === '--agent') options.agents.push(argv[(i += 1)]);
    else if (value === '--all') options.all = true;
    else if (value === '--project') options.project = path.resolve(argv[(i += 1)]);
    else if (value === '--link') options.link = true;
    else if (value === '--home') options.home = path.resolve(argv[(i += 1)]);
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

function runSkills(action, options) {
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
  const passed = results.every((r) => r.passed);
  console.log(JSON.stringify({ passed, entries: results, next: '重新打开 Agent 会话，或按宿主说明刷新技能列表' }, null, 2));
  return passed ? 0 : 1;
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  for (const [command, prefix] of candidates) {
    const probe = spawnSync(command, [...prefix, '-c', 'import sys; print(sys.version_info >= (3, 10))'], {
      encoding: 'utf8',
    });
    if (probe.status === 0 && probe.stdout.trim() === 'True') return [command, prefix];
  }
  return null;
}

function requirePython() {
  const python = findPython();
  if (!python) {
    console.error(JSON.stringify({ error: '需要 Python 3.10 或更高版本，并加入 PATH' }));
    process.exit(1);
  }
  return python;
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
  const python = findPython();
  const report = { node: process.version, platform: `${process.platform} ${os.release()}`, python: null };
  if (python) {
    const [command, prefix] = python;
    const version = spawnSync(command, [...prefix, '--version'], { encoding: 'utf8' });
    report.python = `${command} ${(version.stdout || version.stderr).trim()}`;
    for (const [key, script] of [['ad', 'ad-schematic-layout/scripts/native_ad.py'], ['psim', 'psim-simulation-layout/scripts/native_psim.py']]) {
      const run = spawnSync(command, [...prefix, path.join(ROOT, 'skills', script), 'env'], { encoding: 'utf8' });
      try {
        report[key] = JSON.parse(run.stdout);
      } catch {
        report[key] = { error: (run.stderr || run.stdout).trim() };
      }
    }
  } else report.python = '未找到 Python 3.10+';
  console.log(JSON.stringify(report, null, 2));
  return python ? 0 : 1;
}

function main() {
  const [command = 'help', ...argv] = process.argv.slice(2);
  try {
    const { options, rest } = parse(argv);
    if (command === 'install' || command === 'uninstall' || command === 'check') return runSkills(command, options);
    if (command === 'mcp') return mcp(rest);
    if (command === 'doctor') return doctor();
    console.log(HELP);
    return command === 'help' || command === '--help' ? 0 : 1;
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    return 1;
  }
}

const code = main();
if (typeof code === 'number') process.exitCode = code;
