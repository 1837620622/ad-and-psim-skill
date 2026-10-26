"""整理交付：客户目录只放工程与结果，过程文件另存归档目录，不打压缩包。

两项技能各带一份相同的副本。只复制，不移动或删除工作目录中的任何文件。
"""

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import shutil
import sys

# 交给客户：可编辑工程、仿真结果、正式图纸。
PROJECT = {'.prjpcb', '.schdoc', '.schlib', '.intlib', '.pcbdoc', '.pcblib', '.outjob', '.psimsch', '.dll'}
RESULTS = {'.smv', '.ssf', '.csv'}
DRAWINGS = {'.pdf', '.png', '.svg', '.emf', '.jpg', '.jpeg'}
# 调试草图与软件自动生成的缓存不交付。
DRAFT_MARKS = ('draft', '.render', 'preview')
SKIP_DIRS = {'.git', '__pycache__', '__previews', 'history', '.vscode', '.idea'}
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


def classify(path, include=()):
    name = path.name.lower()
    if any(fnmatch.fnmatch(name, pattern) for pattern in SKIP_FILES):
        return 'skip'
    if any(fnmatch.fnmatch(path.as_posix(), pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in include):
        return 'deliver'
    suffix = path.suffix.lower()
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


def deliver(work, output, name=None, include=(), dry_run=False):
    work, output = Path(work).resolve(), Path(output).resolve()
    if not work.is_dir():
        raise ValueError(f'工作目录不存在：{work}')
    name = name or work.name
    target, archive = output / name, output / f'{name}-archive'
    if output == work or work in output.parents:
        raise ValueError('交付目录不能放在工作目录内部')
    for folder in (target, archive):
        if folder.exists() and any(folder.iterdir()):
            raise FileExistsError(f'目录已存在且非空：{folder}')
    plan = {'deliver': [], 'archive': [], 'skip': []}
    for path in sorted(work.rglob('*')):
        relative = path.relative_to(work)
        if any(part.lower() in SKIP_DIRS for part in relative.parts[:-1]) or not path.is_file():
            continue
        if path.suffix.lower() == '.zip':
            plan['archive'].append(relative)
            continue
        plan[classify(relative, include)].append(relative)
    if not any(p.suffix.lower() in PROJECT for p in plan['deliver']):
        raise ValueError('没有找到工程文件（PrjPcb、SchDoc、psimsch 等），请确认工作目录')
    warnings = []
    suffixes = {p.suffix.lower() for p in plan['deliver']}
    if '.psimsch' in suffixes and not suffixes & {'.smv', '.csv'}:
        warnings.append('有 PSIM 工程但没有仿真结果（SMV/CSV）')
    if '.schdoc' in suffixes and '.prjpcb' not in suffixes:
        warnings.append('有 SchDoc 但没有 PrjPcb 工程文件')
    manifest = {'delivery': str(target), 'archive': str(archive), 'files': [], 'warnings': warnings}
    for kind, root in (('deliver', target), ('archive', archive)):
        for relative in plan[kind]:
            source = work / relative
            entry = {
                'role': kind,
                'path': relative.as_posix(),
                'sha256': sha256(source),
                'bytes': source.stat().st_size,
            }
            manifest['files'].append(entry)
            if dry_run:
                continue
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if sha256(destination) != entry['sha256']:
                raise RuntimeError(f'复制后校验不一致：{relative}')
    if not dry_run:
        archive.mkdir(parents=True, exist_ok=True)
        (archive / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n'
        )
    return {
        'delivery': str(target),
        'archive': str(archive),
        'dry_run': dry_run,
        'delivered': [p.as_posix() for p in plan['deliver']],
        'archived': len(plan['archive']),
        'skipped': len(plan['skip']),
        'warnings': warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='工作目录')
    parser.add_argument('output', type=Path, help='交付根目录；生成 <名称>/ 与 <名称>-archive/')
    parser.add_argument('--name', help='交付名称，默认用工作目录名')
    parser.add_argument(
        '--include', action='append', default=[], help='额外交付的文件（通配符），例如 PSIM 参数文件 params*.txt'
    )
    parser.add_argument('--dry-run', action='store_true', help='只列出分类结果，不复制')
    args = parser.parse_args()
    try:
        result = deliver(args.work, args.output, args.name, args.include, args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
