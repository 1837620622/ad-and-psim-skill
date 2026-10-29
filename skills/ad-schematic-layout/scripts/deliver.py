"""整理交付：客户目录只放模型、图纸和仿真结果，不放 JSON、脚本等过程文件，不打压缩包。

两项技能各带一份相同的副本。只复制，不移动工作目录中的文件；`--clean` 只删除软件会自动重建的缓存。
"""

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

# 交给客户：可编辑工程、仿真结果（含波形 CSV/XLSX）、正式图纸与波形曲线。
PROJECT = {'.prjpcb', '.schdoc', '.schlib', '.intlib', '.pcbdoc', '.pcblib', '.outjob', '.psimsch', '.dll'}
RESULTS = {'.smv', '.ssf', '.csv', '.xlsx', '.xls'}
DRAWINGS = {'.pdf', '.png', '.svg', '.emf', '.jpg', '.jpeg'}
# 硬性规则：计划与报告 JSON、脚本、批处理、日志和压缩包是过程文件，`--include` 也不能把它们放进客户目录。
PROCESS_SUFFIXES = {
    '.json',
    '.py',
    '.pyc',
    '.pyw',
    '.ipynb',
    '.js',
    '.mjs',
    '.bat',
    '.cmd',
    '.ps1',
    '.sh',
    '.vbs',
    '.pas',
    '.log',
    '.zip',
}
# 调试草图与仿原生预览不交付。
DRAFT_MARKS = ('draft', '.render', 'preview')
# 离线预测与预仿真是过程文件（不是原生求解结果）。
PROCESS_DIRS = {'preflight'}
PROCESS_MARKS = ('presim',)
SKIP_DIRS = {'.git', '__pycache__', '__previews', 'history', '.vscode', '.idea', '.pytest_cache', '.ruff_cache'}
SKIP_FILES = (
    '*.pyc',
    '*.bak',
    '*.tmp',
    '~$*',
    '*.schdocpreview',
    '*.pcbdocpreview',
    '*.prjpcbstructure',
    'thumbs.db',
    '.ds_store',
)
# `--clean` 删除的缓存：Python、AD 和操作系统会自动重建，删了不丢工作。History 备份和 *.bak 不删。
CACHE_DIRS = {'__pycache__', '__previews', '.pytest_cache', '.ruff_cache', '.mypy_cache'}
CACHE_FILES = ('*.pyc', '*.pyo', '*.schdocpreview', '*.pcbdocpreview', '*.prjpcbstructure', 'thumbs.db', '.ds_store')


def _included(path, include):
    return any(fnmatch.fnmatch(path.as_posix(), pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in include)


def classify(path, include=()):
    name = path.name.lower()
    if any(fnmatch.fnmatch(name, pattern) for pattern in SKIP_FILES):
        return 'skip'
    suffix = path.suffix.lower()
    if suffix in PROCESS_SUFFIXES:
        return 'archive'
    if _included(path, include):
        return 'deliver'
    if any(part.lower() in PROCESS_DIRS for part in path.parts[:-1]) or any(m in name for m in PROCESS_MARKS):
        return 'archive'
    if suffix in PROJECT or suffix in RESULTS:
        return 'deliver'
    if suffix in DRAWINGS and not any(mark in name for mark in DRAFT_MARKS):
        return 'deliver'
    return 'archive'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def clean(work):
    """删除工作目录里的缓存（不跟随链接），返回删掉的相对路径。"""
    work = Path(work).resolve()
    removed = []
    for folder, dirs, files in os.walk(work):
        here = Path(folder)
        for name in sorted(dirs):
            path = here / name
            if name.lower() in CACHE_DIRS and not path.is_symlink():
                shutil.rmtree(path)
                removed.append(path.relative_to(work).as_posix() + '/')
        dirs[:] = [d for d in dirs if (here / d).is_dir() and not (here / d).is_symlink()]
        for name in sorted(files):
            path = here / name
            if any(fnmatch.fnmatch(name.lower(), pattern) for pattern in CACHE_FILES) and not path.is_symlink():
                path.unlink()
                removed.append(path.relative_to(work).as_posix())
    return removed


def deliver(work, output, name=None, include=(), dry_run=False, archive=False, clean_cache=False):
    work, output = Path(work).resolve(), Path(output).resolve()
    if not work.is_dir():
        raise ValueError(f'工作目录不存在：{work}')
    name = name or work.name
    if not re.fullmatch(r'[\w -]+', name) or name.strip(' .') != name or name in ('.', '..'):
        raise ValueError('交付名称只能含字母、数字、中文、空格、下划线或短横线，不能含路径')
    target, archive_folder = output / name, output / f'{name}-archive'
    folders = (target, archive_folder) if archive else (target,)
    for folder in folders:
        if folder.resolve().parent != output or folder.resolve() == work or work in folder.resolve().parents:
            raise ValueError('交付目录必须位于指定输出目录内，且不能写回工作目录')
    if output == work or work in output.parents:
        raise ValueError('交付目录不能放在工作目录内部')
    for folder in folders:
        if folder.exists() and any(folder.iterdir()):
            raise FileExistsError(f'目录已存在且非空：{folder}')
    plan = {'deliver': [], 'archive': [], 'skip': []}
    warnings = []
    for path in sorted(work.rglob('*')):
        relative = path.relative_to(work)
        if any(part.lower() in SKIP_DIRS for part in relative.parts[:-1]) or not path.is_file():
            continue
        plan[classify(relative, include)].append(relative)
    refused = [p.as_posix() for p in plan['archive'] if p.suffix.lower() in PROCESS_SUFFIXES and _included(p, include)]
    if refused:
        warnings.append('过程文件不进客户目录（JSON、脚本、批处理、日志、压缩包）：' + '、'.join(refused))
    if not any(p.suffix.lower() in PROJECT for p in plan['deliver']):
        raise ValueError('没有找到工程文件（PrjPcb、SchDoc、psimsch 等），请确认工作目录')
    suffixes = {p.suffix.lower() for p in plan['deliver']}
    if '.psimsch' in suffixes and not suffixes & {'.smv', '.csv'}:
        warnings.append('有 PSIM 工程但没有仿真结果（SMV/CSV）')
    if '.schdoc' in suffixes and '.prjpcb' not in suffixes:
        warnings.append('有 SchDoc 但没有 PrjPcb 工程文件')
    manifest = {'delivery': str(target), 'files': [], 'warnings': warnings}
    if archive:
        manifest['archive'] = str(archive_folder)
    occupied = {p.as_posix().casefold() for p in plan['archive']}
    for kind, root in (('deliver', target), ('archive', archive_folder)):
        if kind == 'archive' and not archive:
            continue
        for relative in plan[kind]:
            source = work / relative
            copied_relative = relative
            if kind == 'archive' and relative.as_posix().casefold() == 'manifest.json':
                # 保留输入目录已有的清单，不能被本工具的新清单覆盖。
                number = 0
                while True:
                    copied_relative = Path(f'manifest.source{"-" + str(number) if number else ""}.json')
                    if copied_relative.as_posix().casefold() not in occupied:
                        break
                    number += 1
                occupied.add(copied_relative.as_posix().casefold())
            entry = {
                'role': kind,
                'path': copied_relative.as_posix(),
                'sha256': sha256(source),
                'bytes': source.stat().st_size,
            }
            if copied_relative != relative:
                entry['source_path'] = relative.as_posix()
            manifest['files'].append(entry)
            if dry_run:
                continue
            destination = root / copied_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if sha256(destination) != entry['sha256']:
                raise RuntimeError(f'复制后校验不一致：{relative}')
    if archive and not dry_run:
        archive_folder.mkdir(parents=True, exist_ok=True)
        (archive_folder / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n'
        )
    result = {
        'delivery': str(target),
        'dry_run': dry_run,
        'delivered': [p.as_posix() for p in plan['deliver']],
        'sha256': {e['path']: e['sha256'] for e in manifest['files'] if e['role'] == 'deliver'},
        'not_delivered': [p.as_posix() for p in plan['archive']],
        'skipped': len(plan['skip']),
        'warnings': warnings,
    }
    if archive:
        result['archive'] = str(archive_folder)
    if clean_cache and not dry_run:
        result['cleaned'] = clean(work)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='工作目录')
    parser.add_argument('output', type=Path, help='交付根目录；生成 <名称>/（加 --archive 时另有 <名称>-archive/）')
    parser.add_argument('--name', help='交付名称，默认用工作目录名')
    parser.add_argument(
        '--include', action='append', default=[], help='额外交付的文件（通配符），例如 PSIM 参数文件 params*.txt'
    )
    parser.add_argument('--archive', action='store_true', help='过程文件另存 <名称>-archive/，附 SHA-256 清单')
    parser.add_argument('--clean', action='store_true', help='交付后删除工作目录里的缓存（__pycache__、预览缓存等）')
    parser.add_argument('--dry-run', action='store_true', help='只列出分类结果，不复制')
    args = parser.parse_args()
    try:
        result = deliver(args.work, args.output, args.name, args.include, args.dry_run, args.archive, args.clean)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
