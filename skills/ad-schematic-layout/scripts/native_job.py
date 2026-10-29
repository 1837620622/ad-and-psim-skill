"""Mac/Linux 准备任务，Windows 原生运行，再校验接收原生预览和结果。

不启动网络服务，不捆绑厂商运行时。接收端只验证并复制原图与原始结果，不重新渲染。
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCHEMA = 1
REQUEST = 'native-request.json'
RESULT = 'native-result.json'
RUN_BAT = r"""@echo off
setlocal
cd /d "%~dp0"
set "PY=py -3"
%PY% --version >nul 2>&1 || set "PY=python"
%PY% -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 || goto :nopython
%PY% tool\scripts\native_job.py run . || goto :fail
exit /b 0
:nopython
echo Python 3.11 or newer was not found. Install 64-bit Python from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH", then double-click run.bat again.
goto :stop
:fail
echo Native run failed. Read the message above and native-results\native-result.json.
:stop
if not defined NATIVE_NO_PAUSE pause
exit /b 1
"""


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def safe_file(root, relative):
    """清单里的路径只能落在清单目录内，拒绝盘符、父目录和外部链接。"""
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('清单文件路径无效')
    name = PurePosixPath(relative)
    if name.is_absolute() or not name.parts or '..' in name.parts:
        raise ValueError('清单文件路径越界')
    root = Path(root).resolve()
    path = root.joinpath(*name.parts)
    if not path.resolve().is_relative_to(root):
        raise ValueError('清单文件路径或链接越界')
    return path


def inventory(root):
    return {
        p.relative_to(root).as_posix(): {'sha256': digest(p), 'bytes': p.stat().st_size}
        for p in sorted(root.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.name not in (REQUEST, RESULT) and p.suffix != '.pyc'
    }


def verify_files(root, entries):
    if not isinstance(entries, dict) or not entries:
        raise ValueError('文件清单为空或无效')
    for relative, item in entries.items():
        path = safe_file(root, relative)
        if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError(f'文件缺失或哈希不一致：{relative}')


def empty_folder(path):
    path = Path(path).resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise FileExistsError(f'输出目录已存在且非空：{path}')
    path.mkdir(parents=True, exist_ok=True)
    return path


def command(script, arguments, *, cwd, timeout=180, environment=None):
    done = subprocess.run(
        [sys.executable, str(script), *map(str, arguments)],
        cwd=cwd,
        env=dict(os.environ, PYTHONIOENCODING='utf-8', **(environment or {})),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    stdout, stderr = done.stdout.decode('utf-8', errors='replace'), done.stderr.decode('utf-8', errors='replace')
    try:
        result = json.loads(stdout) if stdout.strip() else None
    except ValueError:
        result = {'stdout': stdout}
    return {'exit_code': done.returncode, 'result': result, 'stderr': stderr.strip()}


def prepare(tool, plan_path, folder, name=None, include=(), reference=None):
    """reference（仅 PSIM）：原始 .psimsch 或 .csv，Windows 求解后与它逐点对照，不一致时任务不通过。"""
    if tool not in ('ad', 'psim') or not (HERE / f'native_{tool}.py').is_file():
        raise ValueError('请从对应 AD 或 PSIM 技能目录准备任务')
    if reference is not None:
        reference = Path(reference).resolve()
        if tool != 'psim' or reference.suffix.lower() not in ('.psimsch', '.csv') or not reference.is_file():
            raise ValueError('原始文件对照只用于 PSIM，须为存在的 .psimsch 或 .csv')
    plan_path = Path(plan_path).resolve()
    plan = read_json(plan_path)
    if not isinstance(plan, dict):
        raise ValueError('计划须为 JSON 对象')
    name = name or plan.get('name') or ('Schematic' if tool == 'ad' else 'PSIM_Model')
    if not isinstance(name, str) or not re.fullmatch(r'[\w-]+', name):
        raise ValueError('任务名称只能含字母、数字、中文、下划线或短横线')
    dependencies = []
    for value in include:
        source = (plan_path.parent / value).resolve()
        if not source.is_relative_to(plan_path.parent):
            raise ValueError(f'依赖须在计划所在目录内：{value}')
        relative = source.relative_to(plan_path.parent).as_posix()
        if not source.is_file() or relative.casefold() == 'plan.json' or source.name in (REQUEST, RESULT):
            raise ValueError('依赖须为计划同目录内的文件，且不能占用 plan.json')
        dependencies.append((source, relative))
    check = command(HERE / f'native_{tool}.py', ['check', plan_path], cwd=plan_path.parent)
    if check['exit_code']:
        raise ValueError('计划预检未通过：' + json.dumps(check, ensure_ascii=False))
    existed = Path(folder).exists()
    folder = empty_folder(folder)
    try:
        return _fill_job(tool, folder, plan, name, dependencies, check, reference)
    except BaseException:
        # 失败时清掉半成品，同一目录可以直接重试；原本就存在的空目录保留。
        for child in folder.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        if not existed:
            folder.rmdir()
        raise


def _fill_job(tool, folder, plan, name, dependencies, check, reference=None):
    plan['name'] = name
    staged_plan = folder / 'input/plan.json'
    write_json(staged_plan, plan)
    for source, relative in dependencies:
        target = safe_file(folder / 'input', relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if reference:
        # 不放进 input/：input/ 会拷进工程和返回结果，原始文件只用来对照。
        (folder / 'reference').mkdir()
        shutil.copy2(reference, folder / 'reference' / reference.name)
    scripts = folder / 'tool/scripts'
    scripts.mkdir(parents=True)
    for source in HERE.glob('*.py'):
        shutil.copy2(source, scripts / source.name)
    native = HERE.parent / 'references/native'
    if native.is_dir():
        target = folder / 'tool/references/native'
        target.mkdir(parents=True)
        for source in native.glob('*.pas'):
            shutil.copy2(source, target / source.name)
    for filename in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        if (HERE.parent / filename).is_file():
            shutil.copy2(HERE.parent / filename, folder / 'tool' / filename)
    (folder / 'run.bat').write_bytes(RUN_BAT.replace('\n', '\r\n').encode('ascii'))
    (folder / 'README.txt').write_text(
        'Windows 原生任务 / Native job for Windows\n\n'
        'Mac/Linux 不安装 AD/PSIM：可查看 preview.render.svg/png 和 AD prepared/ 工程。\n'
        '本地 render 是近似预览；要确认实际软件的效果，用 Windows 返回的原生 PNG。\n\n'
        '将整个目录复制到装有对应软件、Python 3.11+ 和 Pillow 13 的 Windows，双击 run.bat。\n'
        '自动查找失败时设置 AD_EXE 为 X2.EXE，或设置 PSIM_DIR 为 PSIM 安装目录。\n'
        '运行产生 native-results/。将该目录复制回准备任务的电脑，配合原任务运行 receive。\n'
        '失败时窗口停住显示原因；改好后再次双击 run.bat，上次未通过的结果改名为 native-results.failed-N 保留。\n'
        'receive 验证请求、计划和每个文件的 SHA-256，原生图片和数据保持原样。\n\n'
        'No vendor software is needed on Mac/Linux. Use Python 3.11+ and Pillow 13 on the licensed Windows host.\n'
        'Return native-results/ and use receive with the original job. Native PNG/SMV/CSV are copied unchanged.\n'
        'After a failure, fix the cause and run run.bat again; the failed attempt is kept as native-results.failed-N.\n'
        'A portable render is approximate; it is never relabelled as a native export or solver result.\n',
        encoding='utf-8-sig',
    )
    if tool == 'ad':
        created = command(HERE / 'native_ad.py', ['create', staged_plan, folder / 'prepared'], cwd=folder)
        if created['exit_code']:
            raise RuntimeError('生成便携 AD 工程失败：' + json.dumps(created, ensure_ascii=False))
    preview = command(HERE / f'native_{tool}.py', ['render', staged_plan, folder / 'preview.render.svg'], cwd=folder)
    if preview['exit_code']:
        raise RuntimeError('生成便携预览失败：' + json.dumps(preview, ensure_ascii=False))
    if importlib.util.find_spec('PIL') is not None or importlib.util.find_spec('resvg_py') is not None:
        png = command(HERE / f'native_{tool}.py', ['render', staged_plan, folder / 'preview.render.png'], cwd=folder)
        if png['exit_code']:
            raise RuntimeError('生成便携 PNG 失败：' + json.dumps(png, ensure_ascii=False))
    # 离线预测：Windows 运行后与原生结果对照，记录预测是否命中。
    forecast = command(HERE / f'native_{tool}.py', ['preflight', staged_plan, folder / 'preflight'], cwd=folder)
    forecast = forecast['result'] if isinstance(forecast['result'], dict) else {'error': forecast['stderr']}
    request = {
        'schema_version': SCHEMA,
        'tool': tool,
        'name': name,
        'plan_sha256': digest(staged_plan),
        'layout_check': check['result'],
        'preflight': {
            key: forecast.get(key)
            for key in ('ready_for_windows', 'blocking', 'expected_native', 'error')
            if key in forecast
        },
        'portable_preview': {'path': 'preview.render.svg', 'source': 'portable_render', 'native_verified': False},
        'reference': f'reference/{reference.name}' if reference else None,
        'files': inventory(folder),
    }
    write_json(folder / REQUEST, request)
    return {
        'job': str(folder),
        'tool': tool,
        'request_sha256': digest(folder / REQUEST),
        'preview': str(folder / 'preview.render.png')
        if (folder / 'preview.render.png').is_file()
        else str(folder / 'preview.render.svg'),
        'preview_source': 'portable_render',
        'native_verified': False,
        'next': '把整个目录传到 Windows，设置 AD_EXE 或 PSIM_DIR 后双击 run.bat；'
        '将 native-results 目录传回并运行 receive。',
    }


def _set_aside_failed(results):
    """重跑时把上次未通过（或中途停下）的结果改名保留；上次已通过则不动，由 empty_folder 拒绝覆盖。"""
    if not results.is_dir() or not any(results.iterdir()):
        return results
    previous = results / RESULT
    try:
        passed = previous.is_file() and read_json(previous).get('passed') is True
    except (ValueError, AttributeError):
        passed = False
    if not passed:
        number = 1
        while results.with_name(f'{results.name}.failed-{number}').exists():
            number += 1
        results.rename(results.with_name(f'{results.name}.failed-{number}'))
    return results


def run(job, *, ad_exe=None, psim_dir=None, timeout=180):
    if os.name != 'nt':
        raise RuntimeError('run 需要装有相应软件的 Windows；Mac/Linux 使用 handoff 和 receive')
    if not (math.isfinite(timeout) and timeout > 0):
        raise ValueError('timeout 须为有限正数')
    # 原生 PNG 是通过条件之一；先查依赖，免得软件跑完才发现缺 Pillow。
    if importlib.util.find_spec('PIL') is None:
        raise RuntimeError(
            'Windows 执行端缺少 Pillow，无法把原生 EMF 转成 PNG；'
            '先运行 py -3 -m pip install Pillow==13.0.0，再双击 run.bat'
        )
    job = Path(job).resolve()
    request = read_json(job / REQUEST)
    if not isinstance(request, dict):
        raise ValueError('任务清单须为 JSON 对象')
    if request.get('schema_version') != SCHEMA or request.get('tool') not in ('ad', 'psim'):
        raise ValueError('不支持的任务清单')
    verify_files(job, request['files'])
    plan = job / 'input/plan.json'
    if digest(plan) != request['plan_sha256']:
        raise ValueError('计划哈希与请求不一致')
    output = empty_folder(_set_aside_failed(job / 'native-results'))
    tool, name = request['tool'], request['name']
    if not re.fullmatch(r'[\w-]+', name):
        raise ValueError('任务名称无效')
    environment = {}
    if ad_exe:
        environment['AD_EXE'] = str(Path(ad_exe).resolve())
    if psim_dir:
        environment['PSIM_DIR'] = str(Path(psim_dir).resolve())
    script = job / f'tool/scripts/native_{tool}.py'
    project = output / 'project'
    project.mkdir()
    for relative in request['files']:
        if relative.startswith('input/') and relative != 'input/plan.json':
            source = safe_file(job, relative)
            target = safe_file(project, relative[len('input/') :])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    report = {
        'schema_version': SCHEMA,
        'tool': tool,
        'name': name,
        'passed': False,
        'request_sha256': digest(job / REQUEST),
        'plan_sha256': digest(plan),
        'stages': [],
    }

    def stage(label, arguments):
        if tool == 'ad':
            arguments = ['--timeout', str(timeout), *arguments]
        record = command(script, arguments, cwd=project, timeout=timeout + 5, environment=environment)
        record['stage'] = label
        report['stages'].append(record)
        if record['exit_code']:
            check = record['result'].get('reference') if isinstance(record['result'], dict) else None
            if isinstance(check, dict) and check.get('passed') is False:
                report['reference'] = check
                raise RuntimeError(f'仿真结果与原始文件不一致：{check.get("reason") or check.get("equivalence")}')
            raise RuntimeError(f'原生阶段未通过：{label}')
        return record['result']

    try:
        host = stage('environment', ['env'])
        if not host.get('native_available'):
            raise RuntimeError('未找到原生软件；请在 Windows 上设置 AD_EXE 或 PSIM_DIR')
        if tool == 'ad':
            stage('create', ['create', plan, project])
            schematic = project / f'{name}.SchDoc'
            if digest(schematic) != digest(job / f'prepared/{name}.SchDoc'):
                raise RuntimeError('Windows 生成的 SchDoc 与准备端生成的文件字节不一致')
            report['prepared_schdoc_byte_identical'] = True
            expected = project / 'expected.json'
            verified = stage(
                'verify',
                [
                    'verify',
                    project / f'{name}.PrjPcb',
                    output / 'verify',
                    *(['--expected', expected] if expected.is_file() else []),
                ],
            )
            picture = stage('export', ['export', schematic, output / 'drawing'])
            report['forecast'] = _forecast_ad(request, verified)
        else:
            report['solver'] = stage('version', ['version'])
            schematic = project / f'{name}.psimsch'
            stage('create', ['create', plan, schematic])
            reference = request.get('reference')
            reference = ['--reference', safe_file(job, reference)] if reference else []
            simulated = stage('simulate', ['simulate', schematic, output / 'waveforms', *reference])
            if reference:
                report['reference'] = simulated['reference']
            report['forecast'] = _forecast_psim(job / 'preflight/presim.csv', simulated)
            picture = stage('export', ['export', schematic, output / f'drawing/{name}.emf'])
        if not picture.get('text_review', {}).get('passed'):
            raise RuntimeError('原生文字审查未通过')
        png = Path(picture.get('png', ''))
        if not png.is_file():
            raise RuntimeError('Windows 执行端需要 Pillow 生成原生 PNG；EMF 已保留')
        relative = png.relative_to(output).as_posix()
        report.update(passed=True, native_preview={'path': relative, 'source': 'native_export', 'sha256': digest(png)})
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
    report['files'] = inventory(output)
    write_json(output / RESULT, report)
    return dict(report, result_folder=str(output))


def _forecast_ad(request, verified):
    """对照离线预测的编译 warning 数与原生编译结果。"""
    expected = (request.get('preflight') or {}).get('expected_native') or {}
    predicted = expected.get('compile_warnings_missing_footprint')
    actual = (verified or {}).get('warnings')
    return {
        'predicted_compile_warnings': predicted,
        'native_compile_warnings': actual,
        'match': predicted is not None and predicted == actual,
    }


def _forecast_psim(presim, simulated):
    """把离线预仿真波形与 PSIM 原生波形按同一时间点比较；只记录，不影响原生结果是否通过。"""
    if not presim.is_file() or not isinstance(simulated, dict) or not simulated.get('csv'):
        return {'status': 'no_presim'}
    try:
        from compare_results import compare_waveforms

        with presim.open(encoding='utf-8') as stream:
            columns = stream.readline().strip().split(',')
        common = [c for c in columns if c != 'Time' and c in simulated.get('columns', [])]
        if not common:
            return {'status': 'no_common_columns', 'presim_columns': columns}
        result = compare_waveforms(simulated['csv'], presim, signals=common, atol=1e-3, rtol=1e-3)
    except (ValueError, OSError) as error:
        return {'status': 'not_compared', 'reason': str(error)}
    return {
        'status': 'compared',
        'agreement': result['equivalence'],
        'signals': {k: v['max_absolute_error'] for k, v in result['signals'].items()},
        'tolerance': result['tolerances'],
    }


def receive(job, returned, output):
    job, returned = Path(job).resolve(), Path(returned).resolve()
    request = read_json(job / REQUEST)
    report = read_json(returned / RESULT)
    if not isinstance(request, dict) or not isinstance(report, dict):
        raise ValueError('请求和返回清单须为 JSON 对象')
    verify_files(job, request['files'])
    if not report.get('passed') or report.get('schema_version') != SCHEMA:
        raise ValueError('Windows 原生任务未通过，不能作为已验证结果接收')
    if report.get('request_sha256') != digest(job / REQUEST) or report.get('plan_sha256') != request['plan_sha256']:
        raise ValueError('返回结果不属于这份请求或计划')
    if request.get('reference') and not (report.get('reference') or {}).get('passed'):
        raise ValueError('这份任务要求与原始文件对照，返回结果没有通过对照')
    verify_files(returned, report['files'])
    preview = report.get('native_preview', {})
    relative = preview.get('path')
    source = safe_file(returned, relative)
    if relative not in report['files'] or report['files'][relative]['sha256'] != preview.get('sha256'):
        raise ValueError('预览未包含在返回文件清单内')
    with source.open('rb') as stream:
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError('原生预览不是 PNG 文件')
    if (
        preview.get('source') != 'native_export'
        or source.suffix.lower() != '.png'
        or digest(source) != preview.get('sha256')
    ):
        raise ValueError('原生预览来源或哈希无效')
    output = Path(output).resolve()
    if output in (job, returned) or job in output.parents or returned in output.parents:
        raise ValueError('接收目录不能位于输入目录内')
    output = empty_folder(output)
    for filename in report['files']:
        original, target = safe_file(returned, filename), safe_file(output, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    shutil.copy2(returned / RESULT, output / RESULT)
    shutil.copy2(job / REQUEST, output / REQUEST)
    verify_files(output, report['files'])
    received = {
        'passed': True,
        'received': str(output),
        'png': str(safe_file(output, relative)),
        'preview_source': 'native_export',
        'native_verified': True,
        'preview_bytes_identical': digest(safe_file(output, relative)) == preview['sha256'],
        'result_manifest': str(output / RESULT),
    }
    if request.get('reference'):
        received['reference'] = report['reference']
    return received


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('prepare')
    item.add_argument('tool', choices=['ad', 'psim'])
    item.add_argument('plan', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--name')
    item.add_argument('--include', action='append', default=[])
    item.add_argument('--reference', type=Path, help='PSIM：原始 .psimsch 或 .csv，Windows 求解后与它逐点对照')
    item = sub.add_parser('run')
    item.add_argument('job', type=Path)
    item.add_argument('--ad-exe', type=Path)
    item.add_argument('--psim-dir', type=Path)
    item.add_argument('--timeout', type=float, default=180)
    item = sub.add_parser('receive')
    item.add_argument('job', type=Path)
    item.add_argument('returned', type=Path)
    item.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.tool, args.plan, args.folder, args.name, args.include, args.reference)
        elif args.command == 'run':
            result = run(args.job, ad_exe=args.ad_exe, psim_dir=args.psim_dir, timeout=args.timeout)
        else:
            result = receive(args.job, args.returned, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if result.get('passed') is False else 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
