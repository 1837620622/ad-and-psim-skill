"""把两项技能安装到各 Agent 的技能目录。

默认复制到 ~/.agents/skills（Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode 等共用）和
~/.claude/skills（Claude Code）。只替换本安装器装过的目录；同名的其他目录保留并报告冲突。
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('ad-schematic-layout', 'psim-simulation-layout')
MARKER = '.installed-by-ad-and-psim-skill'
# 名称: (用户级目录, 项目级目录)
AGENTS = {
    'universal': ('.agents/skills', '.agents/skills'),
    'claude': ('.claude/skills', '.claude/skills'),
    'codex': ('.agents/skills', '.agents/skills'),
    'gemini': ('.gemini/skills', '.gemini/skills'),
    'copilot': ('.copilot/skills', '.github/skills'),
    'cursor': ('.cursor/skills', '.cursor/skills'),
    'opencode': ('.config/opencode/skills', '.opencode/skills'),
    'zcode': ('.zcode/skills', '.zcode/skills'),
}
DEFAULT = ('universal', 'claude')


def excluded(relative):
    return (
        '__pycache__' in relative.parts
        or relative.suffix == '.pyc'
        or relative.name == MARKER
        or relative.parts[:2] in (('references', 'images'), ('references', 'professional'))
    )


def skill_files(directory):
    """比较整个可分发技能，而不是只比较入口 Markdown。"""
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in directory.rglob('*')
        if p.is_file() and not excluded(p.relative_to(directory))
    }


def ours(target, source):
    if target.is_symlink() or (os.name == 'nt' and target.is_dir() and target.resolve() != target):
        return target.resolve() == source.resolve()
    return (target / MARKER).is_file()


def link(target, source):
    if os.name == 'nt':

        def quote(path):
            return "'" + str(path).replace("'", "''") + "'"

        command = f'New-Item -ItemType Junction -Path {quote(target)} -Target {quote(source)} | Out-Null'
        subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], check=True, capture_output=True
        )
    else:
        target.symlink_to(source, target_is_directory=True)


def remove(target):
    if target.is_symlink() or (os.name == 'nt' and target.resolve() != target):
        # 链接或目录联接只删入口本身，不动仓库里的文件。
        if os.name == 'nt':
            os.rmdir(target)
        else:
            target.unlink()
    else:
        shutil.rmtree(target)


def install(base, mode, check=False, uninstall=False):
    records = []
    for name in SKILLS:
        source, target = ROOT / 'skills' / name, base / name
        record = {'entry': str(target)}
        try:
            exists = os.path.lexists(target)
            if uninstall:
                if exists and ours(target, source):
                    remove(target)
                    record['status'] = 'removed'
                else:
                    record['status'] = 'not installed by this tool'
            elif check:
                if not exists:
                    raise FileNotFoundError('未安装')
                if skill_files(target) != skill_files(source):
                    raise RuntimeError('已安装版本与当前仓库不同，重新运行安装即可更新')
                record['status'] = 'ok'
            else:
                if exists:
                    if not ours(target, source):
                        raise FileExistsError('同名目录不是本安装器创建的，已保留')
                    remove(target)
                base.mkdir(parents=True, exist_ok=True)
                if mode == 'link':
                    link(target, source)
                else:
                    shutil.copytree(
                        source,
                        target,
                        ignore=lambda directory, names, source=source: [
                            n for n in names if excluded((Path(directory) / n).relative_to(source))
                        ],
                    )
                    (target / MARKER).write_text(f'{ROOT}\n', encoding='utf-8')
                record['status'] = 'installed'
            record['passed'] = True
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            record.update(passed=False, error=str(error))
        records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--agent', action='append', choices=sorted(AGENTS), help='目标 Agent，可重复；默认 universal 与 claude'
    )
    parser.add_argument('--all', action='store_true', help='安装到全部已知 Agent 目录')
    parser.add_argument('--project', type=Path, help='安装到项目目录而不是用户目录')
    parser.add_argument('--home', type=Path, default=Path.home(), help=argparse.SUPPRESS)
    parser.add_argument('--link', action='store_true', help='用链接代替复制，便于跟随仓库更新')
    parser.add_argument('--check', action='store_true', help='只检查是否已安装且为最新')
    parser.add_argument('--uninstall', action='store_true', help='删除本安装器装过的入口')
    args = parser.parse_args()
    agents = sorted(AGENTS) if args.all else (args.agent or list(DEFAULT))
    root = (args.project or args.home).resolve()
    bases = {}
    for agent in agents:
        bases.setdefault(root / AGENTS[agent][1 if args.project else 0], []).append(agent)
    results = []
    for base, names in bases.items():
        for record in install(base, 'link' if args.link else 'copy', args.check, args.uninstall):
            results.append(dict(record, agents=names))
    output = {
        'passed': all(r['passed'] for r in results),
        'entries': results,
        'next': '重新打开 Agent 会话，或按宿主说明刷新技能列表',
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output['passed'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
