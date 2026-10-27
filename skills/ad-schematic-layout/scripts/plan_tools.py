"""AD 建模计划工具：把现有 SchDoc 导入为计划、按操作清单修改计划、正交补线。

导入只支持本生成器能重建的图元（矩形符号器件、R/C/L/Y、导线、标号、电源端口、文字）；
带库图形的原生器件会列为 unsupported，应改用 AD 原生脚本编辑。
"""

import copy
import math

from schdoc import DIRECTIONS, pin_end, point

PASSIVES = {'R', 'C', 'L', 'Y'}
DIRECTION_NAMES = ('right', 'up', 'left', 'down')
ELECTRICAL_NAMES = {0: 'input', 1: 'bidirectional', 2: 'output', 3: 'open_collector', 4: 'passive', 7: 'power'}
GROUND_STYLES = {'4', '5', '6'}
# 模型关联无法由基础生成器重建，不能静默丢弃。
IGNORED = ('31', '41')
PART_METADATA = (
    'LIBREFERENCE',
    'LIBRARYPATH',
    'SOURCELIBRARYNAME',
    'SHEETPARTFILENAME',
    'TARGETFILENAME',
    'DESIGNITEMID',
    'UNIQUEID',
    'COMPONENTDESCRIPTION',
)
# AD 标准图幅（10 mil），按 SHEETSTYLE 编号。
SHEET_SIZES = (
    (1150, 760),
    (1550, 1110),
    (2230, 1570),
    (3150, 2230),
    (4460, 3150),
    (950, 750),
    (1500, 950),
    (2000, 1500),
    (3200, 2000),
    (4200, 3200),
    (1100, 850),
    (1400, 850),
    (1700, 1100),
    (990, 790),
    (1540, 990),
    (2060, 1560),
    (3260, 2060),
    (4280, 3260),
)


def sheet_size(sheet):
    if sheet.get('USECUSTOMSHEET') == 'T' or 'SHEETSTYLE' not in sheet:
        return int(float(sheet.get('CUSTOMX', 1150))), int(float(sheet.get('CUSTOMY', 760)))
    style = int(sheet['SHEETSTYLE'])
    return SHEET_SIZES[style] if 0 <= style < len(SHEET_SIZES) else (1150, 760)


def snap(value, grid):
    return round(value / grid) * grid


def route(points, axes, grid=10):
    """把相邻两点之间的斜线补成正交折线；axes 给出端点引脚的出线方向（'H'/'V'/None）。"""
    result = [points[0]]
    for i in range(1, len(points)):
        a, b = result[-1], points[i]
        if a[0] != b[0] and a[1] != b[1]:
            ha, hb = axes[i - 1], axes[i]
            if ha == hb == 'H':
                mx = snap((a[0] + b[0]) / 2, grid)
                result += [(mx, a[1]), (mx, b[1])]
            elif ha == hb == 'V':
                my = snap((a[1] + b[1]) / 2, grid)
                result += [(a[0], my), (b[0], my)]
            elif ha == 'V' or hb == 'H':
                result.append((a[0], b[1]))
            else:
                result.append((b[0], a[1]))
        result.append(b)
    unique = [p for i, p in enumerate(result) if i == 0 or p != result[i - 1]]
    # 零长度导线保持原样，由预检报告，而不是在这里吞掉。
    return unique if len(unique) >= 2 else list(points)


def _children(records, index):
    owner = str(index - 1)
    return [r for r in records if r.get('OWNERINDEX') == owner]


def _number(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def import_records(records, name='Imported'):
    """把 SchDoc 记录转换为计划；返回 (plan, unsupported)。"""
    from check_layout import check_records

    sheet = records[1]
    width, height = sheet_size(sheet)
    plan = {
        'name': name,
        'units': '10mil',
        'grid': int(float(sheet.get('SNAPGRIDSIZE', 10))),
        'canvas': [width, height],
        'parts': [],
        'wires': [],
        'labels': [],
        'power_ports': [],
        'junctions': [],
        'texts': [],
        'border': False,
    }
    unsupported, hot_ends = [], {}
    for index, record in enumerate(records):
        if record.get('RECORD') != '1':
            continue
        children = _children(records, index)
        ref = next((c.get('TEXT') for c in children if c.get('RECORD') == '34'), f'#{index}')
        comment = next((c for c in children if c.get('RECORD') == '41' and c.get('NAME') == 'Comment'), None)
        designator = next((c for c in children if c.get('RECORD') == '34'), None)
        pins = [c for c in children if c.get('RECORD') == '2']
        rects = [c for c in children if c.get('RECORD') == '14']
        others = [c for c in children if c.get('RECORD') not in ('2', '6', '14', '34', '41', *IGNORED)]
        library = record.get('LIBREFERENCE', '')
        texts = {}
        if designator:
            texts['designator_at'] = [_number(v) for v in point(designator)]
        if comment:
            texts['comment_at'] = [_number(v) for v in point(comment)]
        value = comment.get('TEXT', library) if comment else library
        if int(record.get('PARTCOUNT', 2)) > 2 or others:
            unsupported.append({'ref': ref, 'reason': '多部件或含库图形的器件'})
            continue
        if library in PASSIVES and len(pins) == 2:
            center = point(record)
            base = point(pins[0])
            reach = abs(base[0] - center[0]) + abs(base[1] - center[1])
            part = {
                'kind': library,
                'ref': ref,
                'value': value,
                'at': [_number(v) for v in center],
                'vertical': (int(pins[0]['PINCONGLOMERATE']) & 3) in (1, 3),
            }
            if round(reach) != 10:
                part['symbol_scale'] = round(reach / 20, 4)
        elif len(rects) == 1 and not any(c.get('RECORD') == '6' for c in children):
            rect = rects[0]
            x1, y1 = point(rect)
            x2, y2 = point(rect, 'CORNER')
            lengths = {int(float(p.get('PINLENGTH', 20))) for p in pins}
            if len(lengths) > 1:
                unsupported.append({'ref': ref, 'reason': '引脚长度不一致'})
                continue
            part = {
                'kind': 'component',
                'ref': ref,
                'value': value,
                'body': [_number(v) for v in (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))],
                'pins': [
                    {
                        'number': p.get('DESIGNATOR', ''),
                        'name': p.get('NAME', ''),
                        'at': [_number(v) for v in point(p)],
                        'direction': DIRECTION_NAMES[int(p['PINCONGLOMERATE']) & 3],
                        'electrical': ELECTRICAL_NAMES.get(int(p.get('ELECTRICAL', 4)), int(p.get('ELECTRICAL', 4))),
                    }
                    for p in pins
                ],
            }
            if lengths and lengths != {20}:
                part['pin_length'] = lengths.pop()
        else:
            unsupported.append({'ref': ref, 'reason': '符号图形无法用计划表示'})
            continue
        part.update(texts)
        parameters = [copy.deepcopy(c) for c in children if c.get('RECORD') == '41' and c.get('NAME') != 'Comment']
        if parameters:
            part['parameters'] = parameters
        native_properties = {key: record[key] for key in PART_METADATA if key in record}
        if native_properties:
            part['native_properties'] = native_properties
        plan['parts'].append(part)
        for p in pins:
            hot = tuple(_number(v) for v in pin_end(p))
            hot_ends.setdefault(hot, f'{ref}.{p.get("DESIGNATOR", "")}')

    def anchor(x, y):
        key = (_number(x), _number(y))
        return hot_ends.get(key, [key[0], key[1]])

    width_, height_ = plan['canvas']
    for record in records[2:]:
        kind = record.get('RECORD')
        if kind == '1' or record.get('OWNERINDEX', '-1') not in ('', '-1'):
            continue
        if kind == '27':
            count = int(record.get('LOCATIONCOUNT', 0))
            plan['wires'].append([anchor(float(record[f'X{i}']), float(record[f'Y{i}'])) for i in range(1, count + 1)])
        elif kind == '25':
            label = {'name': record.get('TEXT', ''), 'at': anchor(*point(record))}
            if int(record.get('ORIENTATION', 0)):
                label['orientation'] = int(record['ORIENTATION'])
            plan['labels'].append(label)
        elif kind == '17':
            port = {
                'name': record.get('TEXT', ''),
                'at': anchor(*point(record)),
                'ground': record.get('STYLE') in GROUND_STYLES,
            }
            if int(record.get('ORIENTATION', 0)) != (3 if port['ground'] else 1):
                port['orientation'] = int(record.get('ORIENTATION', 0))
            if record.get('STYLE') not in ('2', '4'):
                port['style'] = int(record.get('STYLE', 2))
            plan['power_ports'].append(port)
        elif kind == '29':
            plan['junctions'].append([_number(v) for v in point(record)])
        elif kind == '4':
            plan['texts'].append(
                {
                    'text': record.get('TEXT', ''),
                    'at': [_number(v) for v in point(record)],
                    'font': int(record.get('FONTID', 1)),
                }
            )
        elif kind == '14':
            box = (*point(record), *point(record, 'CORNER'))
            if [round(v) for v in box] == [20, 20, width_ - 20, height_ - 20]:
                plan['border'] = True
            else:
                unsupported.append({'record': kind, 'reason': '图面上的独立矩形'})
        elif kind not in IGNORED:
            unsupported.append({'record': kind, 'reason': '计划格式不支持的图元'})
    for key in ('junctions', 'texts', 'labels', 'power_ports'):
        if not plan[key]:
            del plan[key]
    current, _, _ = check_records(records, None, grid=plan['grid'])
    pin_map = {}
    for line in current['predicted_netlist']:
        net, ref, number = line.split('|')
        pin_map[f'{ref}.{number}'] = net
    if pin_map:
        plan['pin_map'] = pin_map
    return plan, unsupported


def _part(plan, ref):
    for part in plan.get('parts', []):
        if part.get('ref') == ref:
            return part
    raise ValueError(f'计划中没有位号 {ref}')


def _shift(value, dx, dy):
    return [value[0] + dx, value[1] + dy] if isinstance(value, list) else value


def _move_part(part, dx, dy):
    if part['kind'] == 'component':
        x1, y1, x2, y2 = part['body']
        part['body'] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy]
        for pin in part['pins']:
            pin['at'] = _shift(pin['at'], dx, dy)
    else:
        part['at'] = _shift(part['at'], dx, dy)
    for key in ('designator_at', 'comment_at'):
        if key in part:
            part[key] = _shift(part[key], dx, dy)
    for parameter in part.get('parameters', []):
        for axis, delta in (('X', dx), ('Y', dy)):
            field = 'LOCATION.' + axis
            if field in parameter:
                parameter[field] = str(_number(float(parameter[field]) + delta))


def _rename_refs(plan, old, new):
    def swap(value):
        if isinstance(value, str) and value.rpartition('.')[0] == old:
            return new + '.' + value.rpartition('.')[2]
        return value

    plan['wires'] = [[swap(p) for p in wire] for wire in plan.get('wires', [])]
    for key in ('labels', 'power_ports'):
        for item in plan.get(key, []):
            item['at'] = swap(item['at'])
    if 'pin_map' in plan:
        plan['pin_map'] = {swap(k): v for k, v in plan['pin_map'].items()}


def apply_edits(plan, operations):
    """按顺序执行编辑操作，返回新计划；不修改传入对象。"""
    plan = copy.deepcopy(plan)
    for op in operations:
        kind = op.get('op')
        if kind == 'move':
            part = _part(plan, op['ref'])
            if 'to' in op:
                current = part['at'] if part['kind'] != 'component' else part['body'][:2]
                dx, dy = op['to'][0] - current[0], op['to'][1] - current[1]
            else:
                dx, dy = op.get('dx', 0), op.get('dy', 0)
            _move_part(part, dx, dy)
        elif kind == 'set_value':
            _part(plan, op['ref'])['value'] = op['value']
        elif kind == 'move_text':
            field = {'designator': 'designator_at', 'comment': 'comment_at'}[op['field']]
            _part(plan, op['ref'])[field] = list(op['at'])
        elif kind == 'rename':
            _part(plan, op['ref'])['ref'] = op['to']
            _rename_refs(plan, op['ref'], op['to'])
        elif kind == 'add_part':
            plan.setdefault('parts', []).append(copy.deepcopy(op['part']))
        elif kind == 'remove_part':
            _part(plan, op['ref'])
            prefix = op['ref'] + '.'
            plan['parts'] = [p for p in plan['parts'] if p['ref'] != op['ref']]
            plan['wires'] = [
                w for w in plan.get('wires', []) if not any(isinstance(p, str) and p.startswith(prefix) for p in w)
            ]
            for key in ('labels', 'power_ports'):
                if key in plan:
                    plan[key] = [i for i in plan[key] if not (isinstance(i['at'], str) and i['at'].startswith(prefix))]
            if 'pin_map' in plan:
                plan['pin_map'] = {k: v for k, v in plan['pin_map'].items() if not k.startswith(prefix)}
        elif kind == 'add_wire':
            plan.setdefault('wires', []).append(list(op['points']))
        elif kind == 'remove_wire':
            wires = plan.get('wires', [])
            if 'index' in op:
                del wires[op['index']]
            else:
                plan['wires'] = [w for w in wires if op['touching'] not in w]
        elif kind in ('add_label', 'add_power_port'):
            key = 'labels' if kind == 'add_label' else 'power_ports'
            plan.setdefault(key, []).append({k: v for k, v in op.items() if k != 'op'})
        elif kind in ('remove_label', 'remove_power_port'):
            key = 'labels' if kind == 'remove_label' else 'power_ports'
            plan[key] = [
                i
                for i in plan.get(key, [])
                if not (i['name'] == op['name'] and ('at' not in op or i['at'] == op['at']))
            ]
        elif kind == 'set_canvas':
            plan['canvas'] = list(op['canvas'])
        elif kind == 'shift_all':
            _shift_all(plan, op.get('dx', 0), op.get('dy', 0))
        elif kind == 'fit_canvas':
            _fit_canvas(plan, op.get('margin', 40))
        elif kind == 'set_pin_map':
            plan['pin_map'] = dict(op['pin_map'])
        else:
            raise ValueError(f'未知编辑操作：{kind!r}')
    return plan


def _shift_all(plan, dx, dy):
    for part in plan.get('parts', []):
        _move_part(part, dx, dy)
    plan['wires'] = [[_shift(p, dx, dy) for p in wire] for wire in plan.get('wires', [])]
    for key in ('labels', 'power_ports', 'texts'):
        for item in plan.get(key, []):
            item['at'] = _shift(item['at'], dx, dy)
    if 'junctions' in plan:
        plan['junctions'] = [_shift(p, dx, dy) for p in plan['junctions']]


def _fit_canvas(plan, margin):
    from check_layout import check_records
    from native_ad import build

    grid = plan.get('grid', 10)
    result, _, _ = check_records(build(plan).records, None, grid=grid)
    x1, y1, x2, y2 = result['metrics']['content_box']
    border = 20
    dx = snap(border + margin - x1, grid)
    dy = snap(border + margin - y1, grid)
    _shift_all(plan, dx, dy)
    plan['canvas'] = [
        math.ceil((x2 - x1 + 2 * margin) / grid) * grid + 2 * border,
        math.ceil((y2 - y1 + 2 * margin) / grid) * grid + 2 * border,
    ]


def pin_axes(sheet):
    """返回 {位号: {引脚号: 'H'/'V'}}，用于自动补线时决定出线方向。"""
    axes = {}
    owners = {str(i - 1): r for i, r in enumerate(sheet.records) if r.get('RECORD') == '1'}
    refs = {r['OWNERINDEX']: r['TEXT'] for r in sheet.records if r.get('RECORD') == '34'}
    for record in sheet.records:
        if record.get('RECORD') == '2' and record.get('OWNERINDEX') in owners:
            ref = refs.get(record['OWNERINDEX'])
            direction = int(record['PINCONGLOMERATE']) & 3
            axes.setdefault(ref, {})[record['DESIGNATOR']] = 'H' if DIRECTIONS[direction][1] == 0 else 'V'
    return axes
