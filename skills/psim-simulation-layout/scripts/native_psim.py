"""PSIM 命令行：预检、修改计划、便携渲染、Windows 构建包、截图、原生建模求解出图、整理交付。

check/plan-edit/render/presim/waveforms/package/deliver 在任何系统可用；version/inspect/create/edit/simulate/export/
to-python 和窗口截图需要 Windows、PSIM 及其 Python 接口。psimsch 是 PSIM 私有二进制格式，
其他系统通过 package 生成构建包，在 Windows 上由 PSIM 自己写出原生文件。
"""

import argparse
import csv
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PACKAGE_TOOLS = (
    'native_psim.py',
    'check_layout.py',
    'psim_plan.py',
    'review_emf_text.py',
    'native_job.py',
    'compare_results.py',
    'presim.py',
    'render.py',
    'canvas.py',
    'capture.py',
    'analyze_waveform.py',
    'deliver.py',
    'waveforms.py',
    'mcp_server.py',
    'mcp_tools.py',
    'native_discovery.py',
)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n'
    )


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


# ---------------------------------------------------------------- 本机 PSIM ----


def _valid(directory):
    return (directory / 'PSIM2.dll').is_file() and (directory / 'Python' / 'Samples' / 'Psim_Class.py').is_file()


def find_psim(explicit=None):
    """查找 PSIM 安装目录：参数、PSIM_DIR 环境变量、常见安装位置。"""
    # 资源管理器的“复制文件地址”和 set X="..." 都会把引号带进环境变量。
    for candidate in (explicit, os.environ.get('PSIM_DIR', '').strip().strip('"')):
        if candidate and _valid(Path(candidate)):
            return Path(candidate)
    if os.name != 'nt':
        return None
    roots = [Path('C:/Altair'), Path('C:/Powersim'), Path('C:/Siemens')]
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        if os.environ.get(variable):
            roots += [Path(os.environ[variable]) / name for name in ('Altair', 'Powersim', 'Siemens')]
    found = [
        d
        for root in roots
        if root.is_dir()
        for d in [root, *root.glob('*'), *root.glob('*/*')]
        if 'psim' in str(d).lower() and _valid(d)
    ]
    from native_discovery import installed_locations

    found.extend(path for path in installed_locations(r'PSIM') if path.is_dir() and _valid(path))
    return max(found, key=lambda d: [int(n) for n in re.findall(r'\d+', str(d))] or [0]) if found else None


def initialize(explicit=None):
    directory = find_psim(explicit)
    if os.name != 'nt' or directory is None:
        raise RuntimeError('此操作需要 Windows 与 PSIM；可用 --psim-dir 或环境变量 PSIM_DIR 指定安装目录')
    directory = directory.resolve()
    sys.path.insert(0, str(directory / 'Python' / 'Samples'))
    try:
        from Psim_Class import PSIM

        psim = PSIM(str(directory))
    except OSError as error:
        # 32 位或 ARM64 的 Python 载入 x64 的 PSIM2.dll 会报 WinError 193。
        bits = struct.calcsize('P') * 8
        raise RuntimeError(
            f'载入 PSIM 原生接口失败（当前 Python：{platform.machine() or "未知架构"}、{bits} 位）：{error}；'
            '请用与 PSIM 相同架构的 Python（通常是 x64）'
        ) from error
    if not psim or not psim.IsValid():
        raise RuntimeError('PSIM 原生接口初始化失败；确认 PSIM 已激活许可并能正常启动')
    return psim


def inspect(psim, path):
    sch = psim.PsimFileOpen(str(Path(path).resolve()))
    if not sch or not sch.value:
        raise RuntimeError('原生模型打开失败')
    try:
        elements = psim.PsimGetElementList(sch, 1)
        if elements is None:
            raise RuntimeError('原生元件枚举失败')
        # 已测包装器把 Index 固定为 0，不能当作可信索引。
        return [
            {
                'type': e.Type,
                'name': e.Name,
                'wrapper_index': e.Index,
                'index_reliable': False,
                'parameters': {p.Name: str(p.Value) for p in e.Params},
            }
            for e in elements
        ]
    finally:
        sch.free()


def precheck(plan):
    """原生创建前的排版预检；结构错误拒绝创建，近似几何的 warning 随结果返回。"""
    from check_layout import check_plan

    result = check_plan(plan)
    if result['summary']['errors']:
        details = '; '.join(f'{f["code"]}: {f["message"]}' for f in result['findings'] if f['severity'] == 'error')
        raise ValueError(f'排版预检有 error，未创建模型：{details[:600]}')
    return result


def preflight(plan, folder):
    """不装 PSIM 时预测原生结果：排版预检、仿原生预览和线性电路的离线预仿真，给出能否上 Windows 的结论。"""
    from check_layout import check_plan
    from presim import presimulate
    from render import render_plan

    validate(plan)
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    layout = check_plan(plan)
    write_json(folder / 'layout-check.json', layout)
    target = folder / 'preview.png'
    try:
        preview = render_plan(plan, target)
    except (ImportError, RuntimeError):
        preview = render_plan(plan, target.with_suffix('.svg'))
    try:
        simulation = presimulate(plan, folder / 'presim.csv')
    except ValueError as error:
        simulation = {'status': 'not_simulated', 'reason': str(error)}
    blocking = [f'{f["code"]}: {f["message"]}' for f in layout['findings'] if f['severity'] in ('error', 'warning')]
    blocking += [f'{f["code"]}: {f["message"]}' for f in simulation.get('findings', []) if f['severity'] == 'warning']
    return {
        'ready_for_windows': not blocking,
        'blocking': blocking,
        'layout_check': dict(layout['summary'], report=str(folder / 'layout-check.json')),
        'presim': simulation,
        'preview': preview['render'],
        'preview_renderer': preview['renderer'],
        'native_verified': False,
        'note': '离线预测，不代替 PSIM 原生求解和出图；预览为仿原生渲染，预仿真只覆盖线性元件。',
    }


def validate(plan):
    elements = plan.get('elements')
    if not isinstance(elements, list) or not elements:
        raise ValueError('计划须含非空 elements 数组')
    seen = set()
    for element in elements:
        kind, name, attrs = element['type'], element.get('name', ''), element.get('attributes', {})
        if not isinstance(kind, str) or not isinstance(name, str) or not isinstance(attrs, dict):
            raise ValueError('元件的 type、name、attributes 类型错误')
        if kind.upper() not in ('WIRE', 'TEXT', 'TEXTLINK', 'GROUND', 'SIMCONTROL'):
            if not name or name in seen:
                raise ValueError(f'元件名称为空或重复：{name!r}')
            seen.add(name)
        if any('\n' in str(k) or '\n' in str(v) for k, v in attrs.items()):
            raise ValueError('创建参数不能含换行；多行参数文件用原生专用接口')
        if kind.upper() == 'WIRE':
            x1, y1, x2, y2 = (float(attrs[k]) for k in ('X1', 'Y1', 'X2', 'Y2'))
            if x1 != x2 and y1 != y2:
                raise ValueError('WIRE 须为水平或竖直线段')
        for label in element.get('textlinks', []):
            if not all(k in label for k in ('AREA', 'FieldName', 'FieldIndex')):
                raise ValueError('关联文字须含 AREA、FieldName 和本机核实的 FieldIndex')


def create(psim, plan, target, overwrite=False):
    target = Path(target).resolve()
    if target.suffix.lower() != '.psimsch':
        raise ValueError('原生模型扩展名应为 .psimsch')
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    validate(plan)
    sch = psim.PsimFileNew()
    if not sch or not sch.value:
        raise RuntimeError('创建原生文档失败')
    try:
        for element in plan['elements']:
            index = psim.PsimCreateNewElement(
                sch, element['type'], element.get('name', ''), **element.get('attributes', {})
            )
            # 返回创建索引：0 是合法索引，-1 才表示失败。
            if index is None or index == -1:
                raise RuntimeError(f'原生创建失败：{element}')
            for label in element.get('textlinks', []):
                attrs = {
                    'DIRECTION': 0,
                    'PAGE': 0,
                    'XFLIP': 0,
                    '_OPTIONS_': 0,
                    'FontName': 'Arial',
                    'FontSize': -15,
                    'Color': '0',
                    'FontOptions': 65936,
                    'FormatFactor': 18.325623,
                }
                attrs.update(label)
                attrs['OWNERINDEX'] = index
                if psim.PsimCreateNewElement(sch, 'TEXTLINK', '', **attrs) == -1:
                    raise RuntimeError(f'创建原生关联文字失败：{label}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not psim.PsimFileSave(sch, str(target)):
            raise RuntimeError('原生保存失败')
    finally:
        sch.free()
    return inspect(psim, target)


def edit(psim, source, changes, target, overwrite=False):
    target, source = Path(target).resolve(), Path(source).resolve()
    if target == source:
        raise ValueError('修改保存到新副本，不覆盖输入模型')
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    sch = psim.PsimFileOpen(str(source))
    if not sch or not sch.value:
        raise RuntimeError('原生模型打开失败')
    try:
        for change in changes:
            matches = [
                e for e in psim.PsimGetElementList(sch, 1) if e.Type == change['type'] and e.Name == change['name']
            ]
            if len(matches) != 1:
                raise ValueError(f'类型和名称没有唯一匹配：{change}')
            for field, value in change['parameters'].items():
                # 包装器的 Index 不可信，按唯一的类型与名称定位。
                if not psim.PsimSetElmValue2(sch, change['type'], change['name'], field, str(value)):
                    raise RuntimeError(f'原生更新失败：{field}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not psim.PsimFileSave(sch, str(target)):
            raise RuntimeError('原生保存失败')
    finally:
        sch.free()
    return inspect(psim, target)


def simulate(psim, source, folder, parameters):
    source, folder = Path(source).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    graph, table = folder / 'result.smv', folder / 'native.csv'
    if graph.exists() or table.exists():
        raise FileExistsError('仿真输出已存在，请换新目录')
    parameters = dict(parameters, Simview=0)
    result = psim.PsimSimulate(str(source), str(graph), **parameters)
    if result is None or result.Result == 0:
        raise RuntimeError(getattr(result, 'ErrorMessage', '原生求解失败'))
    curves = result.Graph
    if not curves:
        raise RuntimeError('原生求解没有返回波形')
    names, counts = [str(c.Name) for c in curves], [int(c.Rows) for c in curves]
    if len(set(names)) != len(names) or len(set(counts)) != 1 or counts[0] < 2:
        raise RuntimeError('波形列名、长度或样本数量无效')
    time_index = next((i for i, n in enumerate(names) if n.casefold() == 'time'), None)
    if time_index is None:
        raise RuntimeError('原生波形缺少 Time 列')
    previous = None
    with table.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, lineterminator='\r\n')
        writer.writerow(names)
        for i in range(counts[0]):
            row = [float(c.Values[i]) for c in curves]
            if any(not math.isfinite(v) for v in row):
                raise RuntimeError('原生波形含非有限值')
            if previous is not None and row[time_index] <= previous:
                raise RuntimeError('Time 没有严格递增')
            previous = row[time_index]
            writer.writerow(row)
    if not graph.is_file() or not graph.stat().st_size:
        raise RuntimeError('原始 SMV 没有写出')
    return {
        'model_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'solver_version': list(psim.get_psim_version()),
        'parameters': parameters,
        'graph': str(graph),
        'csv': str(table),
        'columns': names,
        'samples': counts[0],
        'waveforms': curves_and_table(table, folder),
    }


def curves_and_table(table, folder):
    """把原生 CSV 画成波形曲线（PNG，无 Pillow 时 SVG）并转成 XLSX；失败只记录原因，不影响原生求解结果。"""
    try:
        from waveforms import waveforms

        made = waveforms(table, folder)
    except (ImportError, ValueError, OSError) as error:
        return {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
    return {'status': 'written', **{k: made[k] for k in ('plot', 'xlsx', 'summary', 'warnings')}}


def to_python(psim, source, target):
    target = Path(target).resolve()
    if target.suffix.lower() != '.py' or target.exists():
        raise ValueError('请指定不存在的 .py 输出路径')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not psim.PsimConvertToPython(str(Path(source).resolve()), str(target)):
        raise RuntimeError('原生转换失败；本机需支持 ConvertToPythonW')
    if not target.is_file() or not target.stat().st_size:
        raise RuntimeError('转换没有写出文件')
    return {'python': str(target), 'note': '只导出未执行；运行前检查脚本与输出路径'}


def text_review(raw):
    """原生 EMF 的文字重叠、越界与压线摘要。"""
    from review_emf_text import review

    try:
        result = review(raw)
    except (ValueError, struct.error) as error:
        return {'status': f'未能审查：{error}'}
    return {
        'passed': not (result['overlaps'] or result['outside_indices'] or result['text_line_conflicts'])
        and result['coverage_complete_for_text_records'],
        'text_count': result['text_count'],
        'overlaps': result['overlaps'][:10],
        'outside': [result['texts'][i]['text'] for i in result['outside_indices']][:10],
        'text_line_conflicts': [
            {k: c[k] for k in ('text', 'box', 'line_count')} for c in result['text_line_conflicts'][:10]
        ],
        'coverage_complete': result['coverage_complete_for_text_records'],
    }


def export(psim, source, target, dpi=120):
    """经 PSIM 原生绘图接口写出 EMF，附完整 PNG、去白边 PNG 与文字审查。"""
    if sys.platform != 'win32':
        raise RuntimeError('原生出图需要 Windows GDI')
    from ctypes import wintypes as w

    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    sch = psim.PsimFileOpen(str(Path(source).resolve()))
    if not sch or not sch.value:
        raise RuntimeError('原生模型打开失败')
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user.CreateWindowExW.argtypes = [
        w.DWORD,
        w.LPCWSTR,
        w.LPCWSTR,
        w.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        w.HWND,
        w.HMENU,
        w.HINSTANCE,
        ctypes.c_void_p,
    ]
    user.CreateWindowExW.restype = w.HWND
    user.DestroyWindow.argtypes, user.DestroyWindow.restype = [w.HWND], w.BOOL
    gdi.CreateEnhMetaFileW.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_void_p, w.LPCWSTR]
    gdi.CreateEnhMetaFileW.restype = w.HDC
    gdi.CloseEnhMetaFile.argtypes, gdi.CloseEnhMetaFile.restype = [w.HDC], w.HANDLE
    gdi.DeleteEnhMetaFile.argtypes, gdi.DeleteEnhMetaFile.restype = [w.HANDLE], w.BOOL
    create_window = psim.psimHandle.CreateSchematicWindow
    create_window.argtypes, create_window.restype = [w.HWND, ctypes.c_int], ctypes.c_int
    draw = psim.psimHandle.ViewSchematicDraw
    draw.argtypes, draw.restype = [ctypes.c_int, w.HDC, ctypes.c_int], ctypes.c_int
    destroy = psim.psimHandle.DestroySchematicWindow
    destroy.argtypes, destroy.restype = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int], ctypes.c_int
    host = dc = None
    created = False
    try:
        host = user.CreateWindowExW(0, 'STATIC', '', 0x80000000, 0, 0, 800, 600, None, None, None, None)
        if not host:
            raise RuntimeError('原生绘图宿主创建失败')
        if not create_window(host, sch.value):
            raise RuntimeError('PSIM 绘图视图创建失败')
        created = True
        dc = gdi.CreateEnhMetaFileW(None, str(target), None, 'PSIM\0Schematic\0\0')
        if not dc:
            raise RuntimeError('EMF 上下文创建失败')
        if not draw(sch.value, dc, 0):
            raise RuntimeError('PSIM 原生绘图失败')
    finally:
        if dc:
            meta = gdi.CloseEnhMetaFile(dc)
            if meta:
                gdi.DeleteEnhMetaFile(meta)
        if created:
            destroy(None, None, sch.value)
        if host:
            user.DestroyWindow(host)
        sch.free()
    raw = target.read_bytes()
    if len(raw) < 88:
        raise RuntimeError('原生 EMF 不完整')
    bounds, device = struct.unpack_from('<4i', raw, 8), struct.unpack_from('<4i', raw, 72)
    if min(device) <= 0:
        raise RuntimeError('EMF 设备信息无效')
    data = bytearray(raw)
    frame = [round(bounds[i] * device[2 + i % 2] * 100 / device[i % 2]) for i in range(4)]
    struct.pack_into('<4i', data, 24, *frame)
    target.write_bytes(data)
    result = {
        'emf': str(target),
        'native_device_bounds': list(bounds),
        'bytes': len(data),
        'graphics_unchanged': data[:24] == raw[:24] and data[40:] == raw[40:],
        'text_review': text_review(bytes(data)),
    }
    try:
        from PIL import Image, ImageChops

        with Image.open(target) as emf:
            emf.load(dpi=dpi)
            picture = emf.convert('RGB')
        full = target.with_suffix('.png')
        picture.save(full)
        box = ImageChops.difference(picture, Image.new('RGB', picture.size, 'white')).getbbox()
        if not box:
            raise RuntimeError('原生导出为空白')
        margin = max(20, round(dpi / 4))
        box = (
            max(0, box[0] - margin),
            max(0, box[1] - margin),
            min(picture.width, box[2] + margin),
            min(picture.height, box[3] + margin),
        )
        compact = target.with_name(f'{target.stem}-compact.png')
        picture.crop(box).save(compact)
        result.update(
            png=str(full), compact_png=str(compact), pixel_size=list(picture.size), blank_crop_bounds=list(box)
        )
    except ImportError:
        result['png_status'] = '需要 Pillow 才能转 PNG；原生 EMF 已保留'
    return result


# ------------------------------------------------------------- 跨系统功能 ----

BUILD_BAT = r"""@echo off
rem Run on a Windows PC with PSIM: PSIM writes the native model, solves it, exports the drawing and opens it.
rem Pure ASCII on purpose; the model name is read from kit.json.
setlocal
cd /d "%~dp0"
set "PY=py -3"
%PY% --version >nul 2>&1 || set "PY=python"
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 || goto :nopython
rem PSIM_DIR is read by Python itself; passing it here would break on a trailing backslash.
%PY% tools\native_psim.py build . || goto :fail
exit /b 0
:nopython
echo Python 3.10 or newer was not found. Install 64-bit Python from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH", then double-click build.bat again.
goto :stop
:fail
echo Build failed. Read the message above; details are in build-report.json.
:stop
if not defined PSIM_NO_PAUSE pause
exit /b 1
"""

PACKAGE_README = """{name} - PSIM 构建包 / PSIM build kit

在装有 PSIM 的 Windows 电脑上双击 build.bat，会依次：
1. 由 PSIM 原生接口按 plan.json 写出 {name}.psimsch；
2. 原生求解，结果写入 result\\（SMV、CSV，波形曲线 waveforms.png 和 Excel 表 waveforms.xlsx）；
3. 原生出图，写入 drawing\\（EMF、PNG）；
4. 用 PSIM 打开做好的 {name}.psimsch（设置环境变量 PSIM_NO_OPEN 可跳过）。
每一步的结果写在 build-report.json；失败时窗口停住显示原因。再次双击会沿用已有的 {name}.psimsch
（不覆盖在 PSIM 里改过的模型），重新求解和出图；要按 plan.json 重新建模，先删掉 {name}.psimsch。
需要 64 位 Python 3.10+；原生 PNG 另需 Python 3.11+ 和 Pillow 13。找不到 PSIM 时先设置环境变量 PSIM_DIR 为安装目录。
psimsch 是 PSIM 的私有格式，只能由 PSIM 自己写出，所以这一步必须在装有 PSIM 的 Windows 上完成。

On a Windows PC with PSIM, double-click build.bat. It writes {name}.psimsch through PSIM's own API,
runs the solver (result\\: SMV, CSV, waveforms.png curves and waveforms.xlsx), exports the drawing
(drawing\\) and opens the model in PSIM (set PSIM_NO_OPEN to skip). Every step is recorded in
build-report.json and the window stays open on failure. Running it again reuses the existing {name}.psimsch
and redoes the solve and drawing; delete the model to rebuild it from plan.json.
Needs 64-bit Python 3.10+; native PNG also needs Python 3.11+ and Pillow 13. Set PSIM_DIR if PSIM is not found.

preview.render.png 是仿原生预览，不是 PSIM 原生导出。
"""
KIT = 'kit.json'


def build(folder, psim_dir=None, psim=None, open_after=None):
    """构建包入口（build.bat 调用）：建模 → 求解 → 出图 → 用 PSIM 打开，每步写入 build-report.json。

    已有模型时沿用，不覆盖用户在 PSIM 里改过的文件；求解和出图只替换本命令自己写出的文件。
    """
    folder = Path(folder).resolve()
    name = read_json(folder / KIT)['name']
    if not isinstance(name, str) or not re.fullmatch(r'[\w-]+', name):
        raise ValueError('kit.json 里的名称无效')
    model, result, drawing = folder / f'{name}.psimsch', folder / 'result', folder / 'drawing'
    report = {'model': str(model), 'passed': False, 'steps': {}}
    if open_after is None:
        open_after = not os.environ.get('PSIM_NO_OPEN')

    def step(number, label):
        print(f'[{number}/4] {label}', file=sys.stderr, flush=True)

    try:
        plan = read_json(folder / 'plan.json')
        layout = precheck(plan)
        psim = psim or initialize(psim_dir)
        step(1, f'建模 {model.name}')
        if model.exists():
            report['steps']['create'] = {
                'status': 'reused',
                'note': f'沿用已有模型；要按 plan.json 重建，先删除 {model.name}',
            }
        else:
            create(psim, plan, model)
            report['steps']['create'] = {'status': 'created', 'layout_check': layout['summary']}
        step(2, '原生求解')
        for old in ('result.smv', 'native.csv', 'waveforms.png', 'waveforms.svg', 'waveforms.xlsx'):
            (result / old).unlink(missing_ok=True)
        report['steps']['simulate'] = simulate(psim, model, result, {})
        step(3, '原生出图')
        for old in (drawing / f'{name}.emf', drawing / f'{name}.png', drawing / f'{name}-compact.png'):
            old.unlink(missing_ok=True)
        report['steps']['export'] = export(psim, model, drawing / f'{name}.emf')
        report['passed'] = report['steps']['export']['text_review'].get('passed', False)
        if not report['passed']:
            report['note'] = (
                '原生出图的文字审查没通过，见 steps.export.text_review；模型已建好，可在 PSIM 里调整后重新出图'
            )
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        if open_after and model.is_file():
            step(4, '用 PSIM 打开模型')
            try:
                report['steps']['open'] = open_model(model, psim_dir)
            except (OSError, RuntimeError) as error:
                report['steps']['open'] = {'status': 'failed', 'note': f'请手动用 PSIM 打开 {model.name}：{error}'}
        write_json(folder / 'build-report.json', report)
    return report


def package(plan_path, folder, name=None):
    """生成 Windows 构建包，由目标版本 PSIM 自己写出文件并求解。"""
    plan_path, folder = Path(plan_path).resolve(), Path(folder).resolve()
    plan = read_json(plan_path)
    validate(plan)
    check = precheck(plan)
    name = name or plan.get('name') or plan_path.stem
    if not re.fullmatch(r'[\w-]+', name):
        raise ValueError('名称只能含字母、数字、中文、下划线或短横线')
    if folder.exists() and any(folder.iterdir()):
        raise FileExistsError(f'目录已存在且非空：{folder}')
    (folder / 'tools').mkdir(parents=True, exist_ok=True)
    write_json(folder / 'plan.json', plan)
    write_json(folder / KIT, {'name': name})
    for tool in PACKAGE_TOOLS:
        shutil.copy2(HERE / tool, folder / 'tools' / tool)
    for filename in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        if (HERE.parent / filename).is_file():
            shutil.copy2(HERE.parent / filename, folder / filename)
    (folder / 'build.bat').write_bytes(BUILD_BAT.replace('\n', '\r\n').encode('ascii'))
    (folder / 'README.txt').write_bytes(PACKAGE_README.format(name=name).replace('\n', '\r\n').encode('utf-8-sig'))
    try:
        from render import render_plan

        render_plan(plan, folder / 'preview.render.png')
    except ImportError:
        pass  # 没有可选 PNG 后端时不生成预览，构建包本身不受影响
    return {
        'package': str(folder),
        'name': name,
        'files': sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()),
        'layout_check': check['summary'],
        'next': '把整个目录拷到装有 PSIM 的 Windows 电脑，双击 build.bat',
    }


def psim_exe(directory):
    exe = next((p for p in (directory / 'PSIM.exe', directory / 'psim.exe') if p.is_file()), None)
    if exe is None:
        raise RuntimeError(f'没有在 {directory} 找到 PSIM.exe')
    return exe


def open_model(source, psim_dir=None):
    """在 Windows 上用 PSIM 打开模型，不等待窗口关闭。"""
    source = Path(source).resolve()
    if source.suffix.lower() != '.psimsch' or not source.is_file():
        raise ValueError('需要已经存在的 .psimsch 文件')
    directory = find_psim(psim_dir)
    if os.name != 'nt' or directory is None:
        raise RuntimeError(
            '打开模型需要 Windows 与 PSIM；psimsch 只能由 PSIM 写出，Mac/Linux 上用 package 或 handoff 交给 Windows'
        )
    exe = psim_exe(directory)
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen([str(exe), str(source)], creationflags=flags, close_fds=True)
    return {'opened': str(source), 'exe': str(exe)}


def screenshot(source, target, psim_dir=None, timeout=180.0):
    """有 PSIM 时打开软件截取窗口；否则按建模计划便携渲染。"""
    source = Path(source)
    directory = find_psim(psim_dir)
    if os.name == 'nt' and directory is not None and source.suffix.lower() == '.psimsch':
        from capture import screenshot as capture

        return capture(source, target, psim_exe(directory), 'PSIM', timeout=timeout)
    from render import render_file

    result = render_file(source, target)
    result['note'] = '本机没有 PSIM，已用便携渲染代替窗口截图'
    return result


def native_look():
    """仿原生出图是否可用，以及用到的字体（真字体还是同度量字体）。"""
    try:
        from canvas import _font_faces, gdi_available

        available = gdi_available()
        fonts = {k: v['family'] for k, v in _font_faces().items()} if available else {}
    except ImportError:
        available, fonts = False, {}
    hint = (
        None
        if available
        else '装 Pillow，并装 Times New Roman/Arial 或同度量的 Liberation 字体（Linux：fonts-liberation）'
    )
    return {'available': available, 'fonts': fonts, 'hint': hint}


def environment(psim_dir=None):
    try:
        import PIL

        pillow = PIL.__version__
    except ImportError:
        pillow = None
    directory = find_psim(psim_dir)
    return {
        'os': platform.system(),
        'python': platform.python_version(),
        'pillow': pillow,
        'native_look': native_look(),
        'psim_dir': str(directory) if directory else None,
        'native_available': os.name == 'nt' and directory is not None,
        'portable_commands': [
            'check',
            'preflight',
            'plan-edit',
            'render',
            'presim',
            'waveforms',
            'package',
            'handoff',
            'receive',
            'compare',
            'deliver',
        ],
        'native_commands': [
            'version',
            'inspect',
            'create',
            'edit',
            'simulate',
            'export',
            'to-python',
            'open',
            'screenshot（窗口）',
        ],
    }


# ---------------------------------------------------------------- 命令行 ----


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--psim-dir', type=Path, help='PSIM 安装目录；默认读 PSIM_DIR 或自动查找')
    parser.add_argument('--report', type=Path, help='把结果 JSON 另存到文件')
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('handoff', help='准备可交给 Windows 原生执行的完整任务')
    item.add_argument('plan', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--name')
    item.add_argument('--include', action='append', default=[])
    item = sub.add_parser('receive', help='接收 Windows 原生图纸和结果，校验文件哈希')
    item.add_argument('job', type=Path)
    item.add_argument('returned', type=Path)
    item.add_argument('output', type=Path)
    item = sub.add_parser('compare', help='比较原生文件哈希或 CSV 波形（不需要 PSIM）')
    item.add_argument('arguments', nargs=argparse.REMAINDER)
    item = sub.add_parser('preflight', help='不装 PSIM 时预测原生结果：预检、仿原生预览、离线预仿真')
    item.add_argument('plan', type=Path)
    item.add_argument('folder', type=Path)
    sub.add_parser('env', help='报告系统、Python、Pillow 与 PSIM 可用性')
    item = sub.add_parser('check', help='排版预检')
    item.add_argument('plan', type=Path)
    item.add_argument('--strict', action='store_true')
    item = sub.add_parser('plan-edit', help='按操作清单修改计划并预检')
    item.add_argument('plan', type=Path)
    item.add_argument('operations', type=Path)
    item.add_argument('output', type=Path)
    item = sub.add_parser('render', help='便携渲染计划为 PNG/SVG')
    item.add_argument('plan', type=Path)
    item.add_argument('target', type=Path)
    item.add_argument('--scale', type=float, help='像素/单位；默认按后端：gdi 用原生导出比例，其余为 4')
    from canvas import add_renderer_arguments

    add_renderer_arguments(item)
    item = sub.add_parser('presim', help='离线预仿真线性电路（不需要 PSIM，结果不是 PSIM 求解）')
    item.add_argument('plan', type=Path)
    item.add_argument('csv', type=Path)
    item = sub.add_parser('waveforms', help='波形 CSV 画成曲线图（PNG/SVG）并转成 Excel 表（XLSX）')
    item.add_argument('csv', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--name', help='输出文件名（不含扩展名），默认 waveforms')
    item.add_argument('--signal', action='append', default=[], help='只画、只导出这些信号，可重复')
    item.add_argument('--start', type=float, help='开始时间 (s)')
    item.add_argument('--end', type=float, help='结束时间 (s)')
    item.add_argument('--svg', action='store_true', help='画 SVG 而不是 PNG')
    item = sub.add_parser('package', help='生成 Windows 一键构建包')
    item.add_argument('plan', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--name')
    item = sub.add_parser('build', help='Windows 构建包入口：建模、求解、出图并用 PSIM 打开（build.bat 调用）')
    item.add_argument('folder', type=Path)
    item.add_argument('--no-open', action='store_true', help='不打开 PSIM（也可设置 PSIM_NO_OPEN）')
    item = sub.add_parser('open', help='Windows：用 PSIM 打开 psimsch')
    item.add_argument('source', type=Path)
    item = sub.add_parser('screenshot', help='有 PSIM 时截取窗口，否则便携渲染')
    item.add_argument('source', type=Path, help='psimsch（Windows）或计划 JSON')
    item.add_argument('target', type=Path)
    item = sub.add_parser('deliver', help='整理客户交付目录（只放模型、图纸和结果）')
    item.add_argument('work', type=Path)
    item.add_argument('output', type=Path)
    item.add_argument('--name')
    item.add_argument('--include', action='append', default=[])
    item.add_argument('--archive', action='store_true', help='过程文件另存 <名称>-archive/')
    item.add_argument('--clean', action='store_true', help='交付后删除工作目录里的缓存')
    sub.add_parser('version', help='原生 API 版本')
    item = sub.add_parser('inspect', help='读取原生元件与参数')
    item.add_argument('source', type=Path)
    item = sub.add_parser('to-python', help='导出原生可重建脚本')
    item.add_argument('source', type=Path)
    item.add_argument('target', type=Path)
    item = sub.add_parser('create', help='按计划创建原生 psimsch')
    item.add_argument('plan', type=Path)
    item.add_argument('target', type=Path)
    item.add_argument('--overwrite', action='store_true')
    item = sub.add_parser('edit', help='原生修改参数并另存')
    item.add_argument('source', type=Path)
    item.add_argument('changes', type=Path)
    item.add_argument('target', type=Path)
    item.add_argument('--overwrite', action='store_true')
    item = sub.add_parser('simulate', help='原生求解并读回波形')
    item.add_argument('source', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--parameters', type=Path)
    item = sub.add_parser('export', help='原生出图并审查文字')
    item.add_argument('source', type=Path)
    item.add_argument('target', type=Path)
    item.add_argument('--dpi', type=int, default=120)
    args = parser.parse_args()
    try:
        if args.command == 'plan-edit' and args.output.resolve() in (args.plan.resolve(), args.operations.resolve()):
            raise ValueError('输出路径不能覆盖输入文件')
        if args.command == 'screenshot':
            if args.target.resolve() == args.source.resolve():
                raise ValueError('输出路径不能覆盖输入文件')
            if args.target.suffix.lower() != '.png':
                raise ValueError('截图输出须为 .png')
        if args.report:
            if args.report.suffix.lower() != '.json':
                raise ValueError('报告输出须为 .json，不能占用工程或图片文件')
            if args.report.exists():
                raise FileExistsError('报告路径已存在，请使用新的路径')
            inputs = [
                getattr(args, k, None)
                for k in ('source', 'plan', 'changes', 'parameters', 'target', 'operations', 'output')
            ]
            if args.report.resolve() in [p.resolve() for p in inputs if p]:
                raise ValueError('报告不能覆盖输入或输出文件')
        command, failed = args.command, False
        if command == 'compare':
            from compare_results import main as compare_main

            return compare_main(args.arguments + (['--output', str(args.report)] if args.report else []))
        if command == 'env':
            data = environment(args.psim_dir)
        elif command == 'check':
            from check_layout import check_plan

            data = check_plan(read_json(args.plan))
            failed = bool(data['summary']['errors'] or (args.strict and data['summary']['warnings']))
        elif command == 'plan-edit':
            from check_layout import check_plan
            from psim_plan import apply_edits

            plan = apply_edits(read_json(args.plan), read_json(args.operations))
            check = check_plan(plan)
            write_json(args.output, plan)
            data = {
                'plan': str(args.output),
                'layout_check': check['summary'],
                'findings': [f for f in check['findings'] if f['severity'] != 'info'],
            }
            failed = bool(check['summary']['errors'])
        elif command == 'render':
            from canvas import renderer_arguments
            from render import render_file

            data = render_file(args.plan, args.target, args.scale, **renderer_arguments(args))
        elif command == 'preflight':
            data = preflight(read_json(args.plan), args.folder)
            failed = not data['ready_for_windows']
        elif command == 'presim':
            from presim import presimulate

            if args.csv.suffix.lower() != '.csv':
                raise ValueError('输出须为 .csv')
            data = presimulate(read_json(args.plan), args.csv)
        elif command == 'waveforms':
            from waveforms import waveforms

            data = waveforms(args.csv, args.folder, args.name, args.signal, args.start, args.end, args.svg)
        elif command == 'package':
            data = package(args.plan, args.folder, args.name)
        elif command == 'build':
            data = build(args.folder, args.psim_dir, open_after=False if args.no_open else None)
            failed = not data['passed']
        elif command == 'open':
            data = open_model(args.source, args.psim_dir)
        elif command == 'screenshot':
            data = screenshot(args.source, args.target, args.psim_dir)
        elif command == 'deliver':
            from deliver import deliver

            data = deliver(
                args.work, args.output, args.name, args.include, archive=args.archive, clean_cache=args.clean
            )
        elif command == 'handoff':
            from native_job import prepare

            data = prepare('psim', args.plan, args.folder, args.name, args.include)
        elif command == 'receive':
            from native_job import receive

            data = receive(args.job, args.returned, args.output)
        else:
            plan = read_json(args.plan) if command == 'create' else None
            layout = precheck(plan) if plan is not None else None
            psim = initialize(args.psim_dir)
            if command == 'version':
                data = {'version': list(psim.get_psim_version()), 'name': psim.get_psim_version_name()}
            elif command == 'inspect':
                data = inspect(psim, args.source)
            elif command == 'to-python':
                data = to_python(psim, args.source, args.target)
            elif command == 'create':
                data = {
                    'elements': create(psim, plan, args.target, args.overwrite),
                    'layout_check': dict(
                        layout['summary'], findings=[f for f in layout['findings'] if f['severity'] != 'info']
                    ),
                }
            elif command == 'edit':
                data = edit(psim, args.source, read_json(args.changes), args.target, args.overwrite)
            elif command == 'simulate':
                data = simulate(psim, args.source, args.folder, read_json(args.parameters) if args.parameters else {})
            else:
                if not 20 <= args.dpi <= 600:
                    raise ValueError('dpi 须在 20–600 之间')
                data = export(psim, args.source, args.target, args.dpi)
                failed = not data['text_review'].get('passed', False)
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        if args.report:
            if args.report.exists():
                raise FileExistsError('报告路径与本次生成的文件冲突，未覆盖生成文件')
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text(text + '\n', encoding='utf-8', newline='\n')
        print(text)
        return 1 if failed else 0
    except Exception as error:  # 命令行统一以 JSON 报错，便于 Agent 读取
        print(json.dumps({'error': str(error), 'type': type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
