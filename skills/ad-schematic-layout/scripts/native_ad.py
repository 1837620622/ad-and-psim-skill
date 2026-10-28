"""AD 原理图命令行：建模、预检、导入与修改、渲染、截图、原生编译与出图、整理交付。

create/check/import/edit/render/deliver 在任何系统可用；verify/export/run-script 和窗口截图需要
Windows 与 Altium Designer。
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent / 'references' / 'native'
DIRECTIONS = {'right': 0, 'up': 1, 'left': 2, 'down': 3}
ELECTRICAL = {'input': 0, 'bidirectional': 1, 'output': 2, 'open_collector': 3, 'passive': 4, 'power': 7}


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def protect_output(target, *sources):
    """输出不能覆盖输入，避免把原生工程误写成计划或图片。"""
    target = Path(target).resolve()
    if target in {Path(source).resolve() for source in sources if source is not None}:
        raise ValueError('输出路径不能覆盖输入文件')


# ------------------------------------------------------------------ 建模 ----


def build(plan):
    """把建模计划转换为内存中的图纸记录，不写文件；create、预检和渲染共用。"""
    from plan_tools import PART_METADATA, pin_axes, route
    from schdoc import Sheet, pin_end
    from tidy_wires import tidy

    if plan.get('units') != '10mil':
        raise ValueError('坐标单位须明确写为 "10mil"')
    width, height = plan['canvas']
    if width <= 0 or height <= 0:
        raise ValueError('画布尺寸须为正数')
    grid, font = plan.get('grid', 10), plan.get('font', 1)
    sheet = Sheet((width, height))
    seen = set()
    for part in plan.get('parts', []):
        ref = part.get('ref')
        if not isinstance(ref, str) or not ref or ref in seen:
            raise ValueError(f'重复或空位号：{ref!r}')
        seen.add(ref)
        kind = part['kind']
        if kind in ('R', 'C', 'L', 'Y'):
            scale = part.get('symbol_scale', 0.5)
            if scale <= 0:
                raise ValueError('symbol_scale 须为正数')
            x, y = part['at']
            index = sheet.passive(
                ref,
                part['value'],
                x,
                y,
                vertical=part.get('vertical', False),
                kind=kind,
                scale=scale,
                grid=grid,
                font=font,
                des_pos=part.get('designator_at'),
                comment_pos=part.get('comment_at'),
            )
        elif kind == 'component':
            pins = part['pins']
            expected = part.get('expected_pin_count')
            if expected is not None and len(pins) != expected:
                raise ValueError(f'引脚总数不符：{ref}')
            if len({str(p['number']) for p in pins}) != len(pins):
                raise ValueError(f'引脚编号重复：{ref}')
            index = sheet.component(
                ref,
                part['value'],
                part['body'],
                [
                    (
                        str(p['number']),
                        p.get('name', ''),
                        *p['at'],
                        DIRECTIONS[p['direction']],
                        p['electrical']
                        if isinstance(p.get('electrical'), int)
                        else ELECTRICAL[p.get('electrical', 'passive')],
                    )
                    for p in pins
                ],
                des_pos=part.get('designator_at'),
                comment_pos=part.get('comment_at'),
                pin_length=part.get('pin_length', 20),
                font=font,
            )
        else:
            raise ValueError(f'基础生成器不支持 {kind!r}；复杂符号用已核实的原生库或本地脚本')
        sheet.records[index].update(
            {k: str(v) for k, v in part.get('native_properties', {}).items() if k in PART_METADATA}
        )
        for parameter in part.get('parameters', []):
            if parameter.get('RECORD', '41') != '41' or parameter.get('NAME') in (None, 'Comment'):
                raise ValueError('附加参数须为带 NAME 的参数记录，不能替换 Comment')
            fields = {k: v for k, v in parameter.items() if k not in ('RECORD', 'OWNERINDEX')}
            sheet.add(41, OWNERINDEX=index - 1, **fields)
        sheet.pins[ref] = {
            r['DESIGNATOR']: pin_end(r)
            for r in sheet.records[index + 1 :]
            if r.get('OWNERINDEX') == str(index - 1) and r.get('RECORD') == '2'
        }
    axes = pin_axes(sheet)

    def position(value):
        if isinstance(value, str):
            ref, _, number = value.rpartition('.')
            if number not in sheet.pins.get(ref, {}):
                raise ValueError(f'引用了不存在的引脚：{value}')
            return sheet.pins[ref][number]
        return tuple(value)

    def axis(value):
        if isinstance(value, str):
            ref, _, number = value.rpartition('.')
            return axes.get(ref, {}).get(number)
        return None

    for wire in plan.get('wires', []):
        points = [position(p) for p in wire]
        if plan.get('autoroute', True):
            points = route(points, [axis(p) for p in wire], grid)
        sheet.wire(*points)
    for label in plan.get('labels', []):
        sheet.label(*position(label['at']), label['name'], label.get('orientation', 0))
    for port in plan.get('power_ports', []):
        index = sheet.power(*position(port['at']), port['name'], ground=port.get('ground', False))
        if 'orientation' in port:
            sheet.records[index]['ORIENTATION'] = str(port['orientation'])
        if 'style' in port:
            sheet.records[index]['STYLE'] = str(port['style'])
    for junction in plan.get('junctions', []):
        sheet.junction(position(junction))
    if plan.get('border', True):
        sheet.rect(20, 20, width - 20, height - 20)
    for text in plan.get('texts', []):
        sheet.text(*text['at'], text['text'], font=text.get('font', font))
    sheet.records = tidy(sheet.records)
    return sheet


def create(plan, folder, allow_layout_errors=False):
    """写出 SchDoc 与 PrjPcb；预检有 error 时拒绝写出。输出在各系统上字节一致。"""
    from check_layout import check_records

    folder = Path(folder).resolve()
    name = plan.get('name', 'Schematic')
    if not re.fullmatch(r'[\w-]+', name):
        raise ValueError('name 只能含字母、数字、中文、下划线或短横线')
    schematic, project = folder / f'{name}.SchDoc', folder / f'{name}.PrjPcb'
    if schematic.exists() or project.exists():
        raise FileExistsError('输出图纸已存在，请使用新的目录')
    sheet = build(plan)
    layout, _, _ = check_records(sheet.records, plan.get('pin_map'), grid=plan.get('grid', 10))
    if layout['summary']['errors'] and not allow_layout_errors:
        details = '; '.join(f'{f["code"]}: {f["message"]}' for f in layout['findings'] if f['severity'] == 'error')
        raise ValueError(f'排版预检有 {layout["summary"]["errors"]} 个 error，未写出图纸：{details[:600]}')
    folder.mkdir(parents=True, exist_ok=True)
    sheet.save(schematic)
    text = (
        f'[Design]\r\nVersion=1.0\r\nHierarchyMode=0\r\n\r\n[Document1]\r\nDocumentPath={schematic.name}\r\n'
        'AnnotationEnabled=1\r\nAnnotateScope=All\r\n'
    )
    project.write_bytes(text.encode('utf-8-sig'))
    if 'pin_map' in plan:
        write_json(folder / 'expected.json', {'pin_map': plan['pin_map']})
    write_json(folder / 'layout-check.json', layout)
    return {
        'schematic': str(schematic),
        'project': str(project),
        'parts': len(plan.get('parts', [])),
        'sha256': hashlib.sha256(schematic.read_bytes()).hexdigest(),
        'layout_check': dict(layout['summary'], report=str(folder / 'layout-check.json')),
        'next': '在 Windows 上运行 verify 与 export 做原生确认',
    }


def preflight(plan, folder):
    """不装 AD 时预测原生结果：排版预检、预测网表、预计的编译 warning 和仿原生预览，给出能否上 Windows 的结论。"""
    from check_layout import check_records
    from render import render_records

    name = plan.get('name', 'Schematic')
    if not isinstance(name, str) or not re.fullmatch(r'[\w-]+', name):
        raise ValueError('name 只能含字母、数字、中文、下划线或短横线')
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    sheet = build(plan)
    layout, _, _ = check_records(sheet.records, plan.get('pin_map'), grid=plan.get('grid', 10))
    write_json(folder / 'layout-check.json', layout)
    # 基础生成器不写封装模型；AD 编译时每个这样的器件报一条缺少封装的 warning（RC 示例实测 4 条）。
    footprints = [
        {'ref': part['ref'], 'message': f'{part["ref"]} 没有封装模型，AD 编译会报缺少封装的 warning'}
        for part in plan.get('parts', [])
        if not part.get('footprint')
    ]
    target = folder / f'{name}.preview.png'
    try:
        preview = render_records(sheet.records, target)
    except (ImportError, RuntimeError):
        preview = render_records(sheet.records, target.with_suffix('.svg'))
    counts = layout['summary']
    topology = not any(f['code'] == 'TOPOLOGY_MISMATCH' for f in layout['findings'])
    blocking = [f'{f["code"]}: {f["message"]}' for f in layout['findings'] if f['severity'] in ('error', 'warning')]
    return {
        'ready_for_windows': not blocking,
        'blocking': blocking,
        'layout_check': dict(counts, report=str(folder / 'layout-check.json')),
        'expected_native': {
            'compile_errors': 0 if topology and not counts['errors'] else None,
            'compile_warnings_missing_footprint': len(footprints),
            'netlist_matches_pin_map': topology if plan.get('pin_map') else None,
        },
        'expected_warnings': footprints,
        'preview': preview['render'],
        'preview_renderer': preview['renderer'],
        'native_verified': False,
        'note': '离线预测，不代替 AD 原生编译和出图；预览为仿原生渲染。',
    }


# ------------------------------------------------------------------ 原生 ----


def find_ad(explicit=None):
    """查找 AD 主程序：参数、AD_EXE 环境变量、常见安装目录。"""
    for candidate in (explicit, os.environ.get('AD_EXE')):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    if os.name != 'nt':
        return None
    found = []
    for root in (os.environ.get('PROGRAMFILES', r'C:\Program Files'), os.environ.get('PROGRAMFILES(X86)', '')):
        if root:
            found += Path(root, 'Altium').glob('*/X2.EXE')
    from native_discovery import installed_locations

    for path in installed_locations(r'Altium Designer'):
        candidate = path / 'X2.EXE' if path.is_dir() else path
        if candidate.name.lower() == 'x2.exe' and candidate.is_file():
            found.append(candidate)
    return max(found, key=lambda p: [int(n) for n in re.findall(r'\d+', p.parent.name)] or [0]) if found else None


def open_project(source, ad_exe=None):
    """在 Windows 上用 AD 打开工程或图纸，不等待窗口关闭；Mac/Linux 生成的文件可以直接这样打开。"""
    source = Path(source).resolve()
    if source.suffix.lower() not in ('.prjpcb', '.schdoc') or not source.is_file():
        raise ValueError('需要已经存在的 .PrjPcb 或 .SchDoc 文件')
    exe = require_ad(ad_exe)
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen([str(exe), str(source)], creationflags=flags, close_fds=True)
    return {'opened': str(source), 'exe': str(exe)}


def require_ad(explicit):
    exe = find_ad(explicit)
    if os.name != 'nt' or exe is None:
        raise RuntimeError('此操作需要 Windows 与 Altium Designer；可用 --ad-exe 或环境变量 AD_EXE 指定 X2.EXE')
    return exe


def invoke(ad_exe, script, procedure, job, timeout):
    if not re.fullmatch(r'[A-Za-z_]\w*', procedure):
        raise ValueError('过程名无效')
    project = job / 'Job.PrjScr'
    project.write_text(f'[Design]\nVersion=1.0\n[Document1]\nDocumentPath={script.name}\n', encoding='ascii')
    argument = f'-RScriptingSystem:RunScript(ProjectName="{project}"|ProcName="{script.name}>{procedure}")'
    # 传入原始 Windows 命令行，保留 AD 脚本分派器需要的引号。
    subprocess.Popen(
        f'"{ad_exe}" {argument}',
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline, status = time.monotonic() + timeout, job / 'status.txt'
    while time.monotonic() < deadline:
        if status.exists():
            text = status.read_text(encoding='utf-8-sig', errors='replace')
            if re.search(r'(?m)^Failed=', text):
                raise RuntimeError('AD 原生脚本报告失败：' + text.strip()[-500:])
            if 'Complete' in text:
                return text
        time.sleep(0.25)
    raise TimeoutError('AD 未在时限内写出完成状态；检查脚本面板，不要把旧输出当成功')


def job_folder():
    job = Path(tempfile.mkdtemp(prefix='ad_native_'))
    if not str(job).isascii():
        raise ValueError('原生脚本需要 ASCII 临时目录，请把 TMP/TEMP 设为英文路径')
    return job


def _decode(data):
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('gb18030')


def verify(ad_exe, project, folder, timeout, expected=None):
    """在副本上原生编译并导出逐引脚网表；可与预期网表比较。"""
    from compare_pin_nets import compare, load_pin_map

    project, folder = Path(project).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    text = _decode(project.read_bytes())
    job = job_folder()
    stage = job / 'source'
    stage.mkdir()
    documents = []

    def stage_document(match):
        source = (project.parent / match.group(1).strip()).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        try:
            relative = source.relative_to(project.parent)
        except ValueError:
            relative = Path('_external') / hashlib.sha256(str(source).encode()).hexdigest()[:12] / source.name
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if source.suffix.lower() == '.schdoc':
            documents.append(target)
        return f'DocumentPath={relative}'

    staged = stage / project.name
    staged.write_text(re.sub(r'(?m)^DocumentPath=([^\r\n]+)', stage_document, text), encoding='utf-8-sig')
    if not documents:
        raise ValueError('工程没有引用 SchDoc')
    (job / 'inputs.txt').write_text('\n'.join(map(str, [staged, *documents])), encoding='utf-16')
    script = (NATIVE / 'VerifyProject.pas').read_text('ascii')
    for placeholder, name in (
        ('__INPUTS__', 'inputs.txt'),
        ('__STATUS__', 'status.txt'),
        ('__MESSAGES__', 'messages.txt'),
        ('__NETS__', 'nets.txt'),
    ):
        script = script.replace(placeholder, str(job / name))
    target = job / 'Verify.pas'
    target.write_text(script, encoding='ascii')
    invoke(ad_exe, target, 'VerifyProject', job, timeout)
    copied = {}
    for name in ('status.txt', 'messages.txt', 'nets.txt'):
        copied[name] = _decode((job / name).read_bytes())
        (folder / name).write_text(copied[name], encoding='utf-8', newline='\n')
    status = copied['status.txt']
    errors = len(re.findall(r'^\[(?:Error|Fatal)\]', status, re.M))
    result = {
        'job': str(job),
        'errors': errors,
        'warnings': len(re.findall(r'^\[Warning\]', status, re.M)),
        'compile_return_true': 'DM_Compile_return=True' in status,
        'cancelled': 'Cancelled=True' in status,
        'netlist': str(folder / 'nets.txt'),
    }
    if expected:
        result['topology'] = compare(load_pin_map(expected), load_pin_map(folder / 'nets.txt'))
    result['passed'] = (
        result['compile_return_true']
        and not result['cancelled']
        and errors == 0
        and result.get('topology', {'match': True})['match']
    )
    return result


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


def export(ad_exe, schematic, folder, timeout, dpi):
    """原生 RedrawToDC 导出 EMF，修正容器物理尺寸，附 PNG 与文字审查。"""
    folder, schematic = Path(folder).resolve(), Path(schematic).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    job = job_folder()
    source = job / 'source.SchDoc'
    shutil.copy2(schematic, source)
    (job / 'inputs.txt').write_text(f'{source}|{job / "native.emf"}', encoding='utf-16')
    script = (NATIVE / 'ExportSchematic.pas').read_text('ascii')
    script = script.replace('__INPUTS__', str(job / 'inputs.txt')).replace('__STATUS__', str(job / 'status.txt'))
    target = job / 'Export.pas'
    target.write_text(script, encoding='ascii')
    invoke(ad_exe, target, 'ExportSchematic', job, timeout)
    raw = (job / 'native.emf').read_bytes()
    data = bytearray(raw)
    bounds, device = struct.unpack_from('<4i', data, 8), struct.unpack_from('<4i', data, 72)
    if min(device) <= 0:
        raise RuntimeError('EMF 设备信息无效')
    frame = [round(bounds[i] * device[2 + i % 2] * 100 / device[i % 2]) for i in range(4)]
    struct.pack_into('<4i', data, 24, *frame)
    emf = folder / f'{schematic.stem}.emf'
    emf.write_bytes(data)
    result = {
        'emf': str(emf),
        'native_original': str(job / 'native.emf'),
        'graphics_unchanged': data[:24] == raw[:24] and data[40:] == raw[40:],
        'text_review': text_review(bytes(data)),
    }
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        with Image.open(emf) as source:
            source.load(dpi=dpi)
            picture = source.convert('RGB')
        picture.save(folder / f'{schematic.stem}.png')
        result.update(png=str(folder / f'{schematic.stem}.png'), pixel_size=list(picture.size))
    except ImportError:
        result['png_status'] = '需要 Pillow 才能转 PNG；原生 EMF 已保留'
    return result


def run_script(ad_exe, script, procedure, timeout):
    job = job_folder()
    source = Path(script).read_text(encoding='utf-8-sig')
    if '__STATUS__' not in source:
        raise ValueError('自定义脚本须用 __STATUS__ 占位写出完成状态')
    target = job / 'Run.pas'
    target.write_text(source.replace('__STATUS__', str(job / 'status.txt')), encoding='ascii')
    return {'status': invoke(ad_exe, target, procedure, job, timeout), 'job': str(job)}


def screenshot(document, target, ad_exe=None, timeout=180.0, scale=None):
    """有 AD 时打开软件截取窗口；没有时用便携渲染生成同样内容的图。"""
    exe = find_ad(ad_exe)
    if os.name == 'nt' and exe is not None:
        from capture import screenshot as capture

        return capture(document, target, exe, 'Altium', timeout=timeout, fit_keys=True)
    from render import render_file

    result = render_file(document, target, scale)
    result['note'] = '本机没有 AD，已用便携渲染代替窗口截图'
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


def environment(ad_exe=None):
    try:
        import PIL

        pillow = PIL.__version__
    except ImportError:
        pillow = None
    exe = find_ad(ad_exe)
    return {
        'os': platform.system(),
        'python': platform.python_version(),
        'pillow': pillow,
        'native_look': native_look(),
        'ad_exe': str(exe) if exe else None,
        'native_available': os.name == 'nt' and exe is not None,
        'portable_commands': [
            'check',
            'preflight',
            'create',
            'import',
            'edit',
            'render',
            'handoff',
            'receive',
            'compare',
            'deliver',
        ],
        'native_commands': ['verify', 'export', 'run-script', 'open', 'screenshot（窗口）'],
    }


# ---------------------------------------------------------------- 命令行 ----


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ad-exe', type=Path, help='X2.EXE 路径；默认读 AD_EXE 或自动查找')
    parser.add_argument('--report', type=Path, help='把结果 JSON 另存到文件')
    parser.add_argument('--timeout', type=float, default=180, help='等待 AD 的秒数')
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
    item = sub.add_parser('compare', help='比较原生文件哈希或 CSV 波形（不需要 AD）')
    item.add_argument('arguments', nargs=argparse.REMAINDER)
    item = sub.add_parser('preflight', help='不装 AD 时预测原生结果：预检、编译 warning、仿原生预览')
    item.add_argument('plan', type=Path)
    item.add_argument('folder', type=Path)
    sub.add_parser('env', help='报告系统、Python、Pillow 与 AD 可用性')
    item = sub.add_parser('check', help='排版预检（不写文件）')
    item.add_argument('plan', type=Path)
    item.add_argument('--preview', type=Path, help='草图 PNG')
    item.add_argument('--strict', action='store_true', help='warning 也算未通过')
    item = sub.add_parser('create', help='按计划写出 SchDoc 与 PrjPcb')
    item.add_argument('plan', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--allow-layout-errors', action='store_true', help='仅调试用：预检有 error 仍写出')
    item = sub.add_parser('import', help='把现有 SchDoc 导入为可编辑计划')
    item.add_argument('schematic', type=Path)
    item.add_argument('plan', type=Path)
    item.add_argument('--allow-partial', action='store_true', help='有无法表示的图元时仍写出计划')
    item = sub.add_parser('edit', help='按操作清单修改计划并预检')
    item.add_argument('plan', type=Path)
    item.add_argument('operations', type=Path, help='JSON 数组，例如 [{"op":"move","ref":"R1","dx":10}]')
    item.add_argument('output', type=Path)
    item = sub.add_parser('render', help='便携渲染 SchDoc 或计划为 PNG/SVG')
    item.add_argument('source', type=Path)
    item.add_argument('target', type=Path)
    item.add_argument('--scale', type=float, help='像素/单位；默认按后端：gdi 用原生导出比例，其余为 4')
    from canvas import add_renderer_arguments

    add_renderer_arguments(item)
    item = sub.add_parser('open', help='Windows：用 AD 打开工程或图纸')
    item.add_argument('source', type=Path)
    item = sub.add_parser('screenshot', help='有 AD 时截取软件窗口，否则仿原生渲染')
    item.add_argument('schematic', type=Path)
    item.add_argument('target', type=Path)
    item = sub.add_parser('verify', help='原生编译与逐引脚网表')
    item.add_argument('project', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--expected', type=Path)
    item = sub.add_parser('export', help='原生导出 EMF/PNG 并审查文字')
    item.add_argument('schematic', type=Path)
    item.add_argument('folder', type=Path)
    item.add_argument('--dpi', type=int, default=20)
    item = sub.add_parser('run-script', help='执行本地 DelphiScript')
    item.add_argument('script', type=Path)
    item.add_argument('procedure')
    item = sub.add_parser('deliver', help='整理交付目录与归档目录')
    item.add_argument('work', type=Path)
    item.add_argument('output', type=Path)
    item.add_argument('--name')
    item.add_argument('--include', action='append', default=[])
    args = parser.parse_args()
    try:
        if args.timeout <= 0:
            raise ValueError('timeout 须为正数')
        if args.command == 'import':
            protect_output(args.plan, args.schematic)
        elif args.command == 'edit':
            protect_output(args.output, args.plan, args.operations)
        elif args.command == 'render':
            protect_output(args.target, args.source)
        elif args.command == 'screenshot':
            protect_output(args.target, args.schematic)
            if args.target.suffix.lower() != '.png':
                raise ValueError('截图输出须为 .png')
        elif args.command == 'check' and args.preview:
            protect_output(args.preview, args.plan)
        if args.report:
            if args.report.suffix.lower() != '.json':
                raise ValueError('报告输出须为 .json，不能占用工程或图片文件')
            if args.report.exists():
                raise FileExistsError('报告路径已存在，请使用新的路径')
            inputs = [
                getattr(args, k, None)
                for k in (
                    'plan',
                    'project',
                    'expected',
                    'schematic',
                    'script',
                    'operations',
                    'source',
                    'output',
                    'target',
                )
            ]
            if args.report.resolve() in [p.resolve() for p in inputs if p]:
                raise ValueError('报告不能覆盖输入文件')
        command = args.command
        if command == 'compare':
            from compare_results import main as compare_main

            return compare_main(args.arguments + (['--output', str(args.report)] if args.report else []))
        failed = False
        if command == 'env':
            result = environment(args.ad_exe)
        elif command == 'check':
            from check_layout import check_plan

            result = check_plan(read_json(args.plan), args.preview)
            failed = bool(result['summary']['errors'] or (args.strict and result['summary']['warnings']))
        elif command == 'preflight':
            result = preflight(read_json(args.plan), args.folder)
            failed = not result['ready_for_windows']
        elif command == 'create':
            result = create(read_json(args.plan), args.folder, args.allow_layout_errors)
        elif command == 'import':
            from plan_tools import import_records
            from schdoc import read

            plan, unsupported = import_records(read(args.schematic), args.schematic.stem)
            result = {'plan': str(args.plan), 'parts': len(plan['parts']), 'unsupported': unsupported}
            if unsupported and not args.allow_partial:
                failed = True
                result['status'] = '有无法用计划表示的图元，未写出；可加 --allow-partial，或在 Windows 上用原生脚本修改'
            else:
                write_json(args.plan, plan)
        elif command == 'edit':
            from check_layout import check_plan
            from plan_tools import apply_edits

            plan = apply_edits(read_json(args.plan), read_json(args.operations))
            check = check_plan(plan)
            write_json(args.output, plan)
            result = {
                'plan': str(args.output),
                'layout_check': check['summary'],
                'findings': [f for f in check['findings'] if f['severity'] != 'info'],
            }
            failed = bool(check['summary']['errors'])
        elif command == 'render':
            from canvas import renderer_arguments
            from render import render_file

            result = render_file(args.source, args.target, args.scale, **renderer_arguments(args))
        elif command == 'open':
            result = open_project(args.source, args.ad_exe)
        elif command == 'screenshot':
            result = screenshot(args.schematic, args.target, args.ad_exe, args.timeout)
        elif command == 'deliver':
            from deliver import deliver

            result = deliver(args.work, args.output, args.name, args.include)
        elif command == 'handoff':
            from native_job import prepare

            result = prepare('ad', args.plan, args.folder, args.name, args.include)
        elif command == 'receive':
            from native_job import receive

            result = receive(args.job, args.returned, args.output)
        else:
            exe = require_ad(args.ad_exe)
            if command == 'verify':
                result = verify(exe, args.project, args.folder, args.timeout, args.expected)
                failed = not result['passed']
            elif command == 'export':
                result = export(exe, args.schematic, args.folder, args.timeout, args.dpi)
                failed = not result['text_review'].get('passed', False)
            else:
                result = run_script(exe, args.script, args.procedure, args.timeout)
        if args.report:
            if args.report.exists():
                raise FileExistsError('报告路径与本次生成的文件冲突，未覆盖生成文件')
            write_json(args.report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if failed else 0
    except Exception as error:  # 命令行统一以 JSON 报错，便于 Agent 读取
        print(json.dumps({'error': str(error), 'type': type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
