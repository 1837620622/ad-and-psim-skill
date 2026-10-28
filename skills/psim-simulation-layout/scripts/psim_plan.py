"""PSIM 建模计划：元件几何、端口、关联文字和编辑操作。坐标 y 向下。

SYMBOLS 中的几何按 PSIM 2026 原生导出标定（DIRECTION=0，相对首端口）；其余元件只知道首端口。
"""

import copy
import math
from collections import defaultdict
import re

# box 是整体外框；parts 把引线和图形主体分开（圆形写作 ('circle', 圆心 x, 圆心 y, 半径)），
# 判断文字压符号时用，避免把引线两侧和圆外的空白算作符号。
SYMBOLS = {
    'R': {
        'ports': [(0, 0), (50, 0)],
        'box': (0, -7, 50, 7),
        'parts': [(0, -1, 10, 1), (10, -7, 41, 7), (41, -1, 50, 1)],
    },
    'C': {
        'ports': [(0, 0), (50, 0)],
        'box': (0, -8, 50, 8),
        'parts': [(0, -1, 23, 1), (22, -8, 28, 8), (27, -1, 50, 1)],
    },
    'L': {'ports': [(0, 0), (50, 0)], 'box': (0, -8, 50, 2), 'calibrated': False},
    'VDC': {
        'ports': [(0, 0), (0, 50)],
        'box': (-11, 0, 11, 50),
        'parts': [(-1, 0, 1, 15), ('circle', 0, 25, 10.5), (-1, 35, 1, 50)],
    },
    'VSIN': {'ports': [(0, 0), (0, 50)], 'box': (-11, 0, 11, 50), 'calibrated': False},
    'VP': {'ports': [(0, 0)], 'box': (-11, -31, 11, 0), 'parts': [(-1, -10, 1, 0), ('circle', 0, -20, 10.5)]},
    'GROUND': {'ports': [(0, 0)], 'box': (-7, 0, 7, 17)},
}
CLOCK_RADIUS = 20
CLOCK_BOX = (-21, -21, 21, 21)
NAMELESS = {'WIRE', 'TEXT', 'TEXTLINK', 'GROUND', 'SIMCONTROL'}


def point(value):
    """解析 "{x,y}" 或 [x, y]。"""
    if isinstance(value, str):
        numbers = re.findall(r'-?\d+(?:\.\d+)?', value)
        if len(numbers) < 2:
            raise ValueError(f'无法解析坐标：{value!r}')
        return float(numbers[0]), float(numbers[1])
    return float(value[0]), float(value[1])


def format_point(p):
    x, y = (int(v) if float(v).is_integer() else v for v in p)
    return f'{{{x},{y}}}'


def rotate(offset, direction):
    """按 DIRECTION（度，屏幕上顺时针）旋转局部偏移。"""
    u, v = offset
    for _ in range(int(float(direction)) // 90 % 4):
        u, v = -v, u
    return u, v


def place(box, origin, direction):
    corners = [rotate(c, direction) for c in ((box[0], box[1]), (box[2], box[3]))]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return origin[0] + min(xs), origin[1] + min(ys), origin[0] + max(xs), origin[1] + max(ys)


def kind(element):
    return str(element.get('type', '')).upper()


def origin(element):
    attrs = element.get('attributes', {})
    if 'PORTS' in attrs:
        return point(attrs['PORTS'])
    if 'POINT' in attrs:
        return point(attrs['POINT'])
    return None


def ports(element):
    """已标定元件返回全部端口，其他元件只返回首端口。"""
    start = origin(element)
    if start is None or kind(element) == 'SIMCONTROL':
        return []
    symbol = SYMBOLS.get(kind(element))
    direction = element.get('attributes', {}).get('DIRECTION', 0)
    offsets = symbol['ports'] if symbol else [(0, 0)]
    return [(start[0] + du, start[1] + dv) for du, dv in (rotate(o, direction) for o in offsets)]


def symbol_parts(element):
    """符号的分块范围（引线与主体分开）；没有分块数据时退回整体外框。"""
    start = origin(element)
    symbol = SYMBOLS.get(kind(element))
    if start is None or symbol is None or 'parts' not in symbol:
        box = symbol_box(element)
        return [box] if box else []
    direction = element.get('attributes', {}).get('DIRECTION', 0)
    result = []
    for part in symbol['parts']:
        if part[0] == 'circle':
            du, dv = rotate(part[1:3], direction)
            result.append(('circle', start[0] + du, start[1] + dv, part[3]))
        else:
            result.append(place(part, start, direction))
    return result


def part_overlaps(part, box, inset=0.0):
    """符号分块与矩形是否重叠；圆形按到圆心的最近距离判断。"""
    if part[0] == 'circle':
        _, cx, cy, r = part
        dx = max(box[0] - cx, 0, cx - box[2])
        dy = max(box[1] - cy, 0, cy - box[3])
        return dx * dx + dy * dy < (r - inset) ** 2
    return min(part[2], box[2]) - max(part[0], box[0]) > inset and min(part[3], box[3]) - max(part[1], box[1]) > inset


def symbol_box(element):
    start = origin(element)
    if start is None:
        return None
    if kind(element) == 'SIMCONTROL':
        return place(CLOCK_BOX, start, 0)
    symbol = SYMBOLS.get(kind(element))
    return place(symbol['box'], start, element.get('attributes', {}).get('DIRECTION', 0)) if symbol else None


def wire_points(element):
    a = element['attributes']
    return (float(a['X1']), float(a['Y1'])), (float(a['X2']), float(a['Y2']))


def on_segment(p, segment):
    a, b = segment
    return (
        a[0] == b[0] == p[0]
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
        or a[1] == b[1] == p[1]
        and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
    )


def port_nets(plan):
    """已知端口的同网伙伴；未标定器件仅有首端口，不能取代原生网表。"""
    parent, names, counts, grounds = {}, {}, defaultdict(int), []

    def find(p):
        parent.setdefault(p, p)
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(a, b):
        parent[find(a)] = find(b)

    wires = []
    for e in plan['elements']:
        if kind(e) == 'WIRE':
            a, b = wire_points(e)
            wires.append((a, b))
            union(a, b)
            continue
        prefix = f'{kind(e)}:{e.get("name", "")}'
        counts[prefix] += 1
        for number, p in enumerate(ports(e), 1):
            names[f'{prefix}#{counts[prefix]}.{number}'] = p
            find(p)
            if kind(e) == 'GROUND':
                grounds.append(p)
    points = list(parent)
    for segment in wires:
        for p in points:
            if on_segment(p, segment):
                union(segment[0], p)
    for p in grounds[1:]:
        union(grounds[0], p)
    groups = defaultdict(list)
    for name, p in names.items():
        groups[find(p)].append(name)
    return {name: tuple(sorted(groups[find(p)])) for name, p in names.items()}


def make_wire(a, b):
    def number(v):
        return int(v) if float(v).is_integer() else v

    return {
        'type': 'WIRE',
        'name': '',
        'attributes': {'X1': number(a[0]), 'Y1': number(a[1]), 'X2': number(b[0]), 'Y2': number(b[1])},
    }


def crosses(segment, box):
    """正交线段是否进入矩形内部（只碰边不算）。"""
    (x1, y1), (x2, y2) = segment
    if x1 == x2:
        return box[0] < x1 < box[2] and min(y1, y2) < box[3] and max(y1, y2) > box[1]
    return box[1] < y1 < box[3] and min(x1, x2) < box[2] and max(x1, x2) > box[0]


def square(a, b, obstacles=()):
    """把斜线拆成两段正交线；优先选不穿过元件符号的拐角。"""
    if a[0] == b[0] or a[1] == b[1]:
        return [make_wire(a, b)]
    options = [(b[0], a[1]), (a[0], b[1])]
    corner = next(
        (c for c in options if not any(crosses(seg, box) for seg in ((a, c), (c, b)) for box in obstacles)), options[0]
    )
    return [make_wire(a, corner), make_wire(corner, b)]


# 关联文字的原生位置（按 PSIM 2026 原生导出标定）：起点 = AREA 水平中心 - FormatFactor，
# 基线 = AREA 上边 + TEXT_BASELINE·|FontSize|，字号 em = TEXT_EM·|FontSize|。
FORMAT_FACTOR = 18.325623
TEXT_EM = 6 / 7
TEXT_BASELINE = 0.76


# Arial（与 Liberation Sans 度量相同）ASCII 32..126 的字宽，单位 1/1000 em。
ARIAL = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778,
    722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
    278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)  # fmt: skip
DESCENDERS = set('gjpqy(),;_[]{}|')


def text_box(element, label):
    """关联文字在原生图上的大致墨迹框 (x1, y1, x2, y2)：按原生定位规则和 Arial 字宽估算。"""
    x, baseline, em = text_origin(label)
    value = display_text(element, label.get('FieldName', ''))
    width = sum(ARIAL[ord(c) - 32] if 32 <= ord(c) < 127 else 1000 for c in value) / 1000 * em
    low = 0.21 * em if DESCENDERS & set(value) or any(ord(c) > 0x2E80 for c in value) else 0
    return (x, baseline - 0.72 * em, x + width, baseline + low)


def text_origin(label):
    """返回关联文字的 (起点 x, 基线 y, em)，单位与计划坐标相同。"""
    x1, y1, x2, _ = (float(v) for v in label['AREA'])
    size = abs(float(label.get('FontSize', -15)))
    factor = float(label.get('FormatFactor', FORMAT_FACTOR))
    return (x1 + x2) / 2 - factor, y1 + TEXT_BASELINE * size, TEXT_EM * size


def display_text(element, field):
    if field == 'Name':
        return element.get('name', '')
    value = element.get('attributes', {}).get(field, '')
    return repr(value) if isinstance(value, float) else str(value)


def _find(plan, op):
    elements = plan['elements']
    if op.get('name'):
        matches = [e for e in elements if e.get('name') == op['name'] and kind(e) != 'WIRE']
    else:
        matches = [e for e in elements if kind(e) == str(op.get('type', '')).upper()]
    if len(matches) != 1:
        raise ValueError(f'没有唯一匹配的元件：{op.get("name") or op.get("type")}')
    return matches[0]


def _shift_element(element, dx, dy):
    attrs = element['attributes']
    for key in ('PORTS', 'POINT'):
        if key in attrs:
            x, y = point(attrs[key])
            attrs[key] = format_point((x + dx, y + dy))
    for label in element.get('textlinks', []):
        x1, y1, x2, y2 = label['AREA']
        label['AREA'] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy]


def apply_edits(plan, operations):
    """按顺序执行编辑操作，返回新计划；不修改传入对象。"""
    plan = copy.deepcopy(plan)
    elements = plan['elements']
    for op in operations:
        action = op.get('op')
        if action == 'move':
            element = _find(plan, op)
            before = port_nets(plan)
            dx, dy = op.get('dx', 0), op.get('dy', 0)
            if 'to' in op:
                current = origin(element)
                dx, dy = op['to'][0] - current[0], op['to'][1] - current[1]
            attached = set(ports(element))
            old_wires = [wire_points(e) for e in elements if kind(e) == 'WIRE']
            stationary_ports = {p for e in elements if e is not element and kind(e) != 'WIRE' for p in ports(e)}
            shared = {
                p
                for p in attached
                if p in stationary_ports
                or any(on_segment(p, w) and p not in w for w in old_wires)
                or sum(p in w for w in old_wires) > 1
            }
            _shift_element(element, dx, dy)
            obstacles = [box for box in map(symbol_box, elements) if box]
            moved = []
            for wire in [e for e in elements if kind(e) == 'WIRE']:
                a, b = wire_points(wire)
                dragged = attached - shared
                if a in dragged or b in dragged:
                    a = (a[0] + dx, a[1] + dy) if a in dragged else a
                    b = (b[0] + dx, b[1] + dy) if b in dragged else b
                    elements.remove(wire)
                    moved += square(a, b, obstacles)
            elements.extend(moved)
            if dx or dy:
                for p in sorted(shared):
                    elements.extend(square((p[0] + dx, p[1] + dy), p, obstacles))
            if port_nets(plan) != before:
                raise ValueError('移动后的已知端口拓扑发生变化，未保存；请调整位置或走线')
        elif action == 'set':
            _find(plan, op).setdefault('attributes', {})[op['field']] = op['value']
        elif action == 'move_text':
            element = _find(plan, op)
            label = next((t for t in element.get('textlinks', []) if t['FieldName'] == op['field']), None)
            if label is None:
                raise ValueError(f'{element.get("name")} 没有关联文字 {op["field"]}')
            if 'area' in op:
                label['AREA'] = list(op['area'])
            else:
                x1, y1, x2, y2 = label['AREA']
                dx, dy = op.get('dx', 0), op.get('dy', 0)
                label['AREA'] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy]
        elif action == 'add_element':
            elements.append(copy.deepcopy(op['element']))
        elif action == 'remove_element':
            elements.remove(_find(plan, op))
        elif action == 'add_wire':
            obstacles = [box for box in map(symbol_box, elements) if box]
            elements.extend(square(tuple(op['from']), tuple(op['to']), obstacles))
        elif action == 'remove_wire':
            target = tuple(op['at'])
            plan['elements'] = elements = [e for e in elements if not (kind(e) == 'WIRE' and target in wire_points(e))]
        elif action == 'shift_all':
            dx, dy = op.get('dx', 0), op.get('dy', 0)
            for element in elements:
                if kind(element) == 'WIRE':
                    a, b = wire_points(element)
                    element.update(make_wire((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy)))
                else:
                    _shift_element(element, dx, dy)
        elif action == 'place_text':
            plan = place_text(plan, op.get('names'), reset=bool(op.get('all')))
            elements = plan['elements']
        else:
            raise ValueError(f'未知编辑操作：{action!r}')
    return plan


TEXT_CODES = ('TEXT_OVERLAP', 'TEXT_ON_SYMBOL', 'TEXT_ON_WIRE', 'TEXT_NEAR_LINE')
LINE = 17  # 一行关联文字的 AREA 高度（FontSize -15）


def _text_problems(plan):
    from check_layout import check_plan

    return [f for f in check_plan(plan)['findings'] if f['code'] in TEXT_CODES]


def _area(start, top, label, element):
    """文字起点为 start 时的 AREA：中心 = 起点 + FormatFactor，宽度按文字长度留余量。"""
    factor = float(label.get('FormatFactor', FORMAT_FACTOR))
    x1, _, x2, _ = text_box(element, dict(label, AREA=[0, 0, 0, 0]))
    width = max(24, math.ceil(x2 - x1) + 6)
    center = start + factor
    return [round(center - width / 2), round(top), round(center - width / 2) + width, round(top) + LINE]


def _text_candidates(element):
    """按排版规则给出候选：横放元件在上方或下方，竖放元件在右侧或左侧，探头名在探头右侧或左侧。"""
    labels = element.get('textlinks', [])
    box = symbol_box(element)
    start = origin(element)
    if not labels or start is None:
        return []
    if box is None:
        box = (start[0] - 10, start[1] - 10, start[0] + 10, start[1] + 10)
    x1, y1, x2, y2 = box
    widths = []
    for label in labels:
        a, _, b, _ = text_box(element, dict(label, AREA=[0, 0, 0, 0]))
        widths.append(b - a)
    block = LINE * len(labels)
    t = kind(element)
    if t == 'VP':
        cy = start[1] - 20
        order = [((x2 + 2, cy - 8), (1, 0)), ((x1 - 3 - max(widths), cy - 8), (-1, 0))]
    else:
        middle = (y1 + y2) / 2
        right = ((x2 + 3, middle - block / 2), (1, 0))
        left = ((x1 - 4 - max(widths), middle - block / 2), (-1, 0))
        above = ((x1 + 7, y1 - 4 - block), (0, -1))
        below = ((x1 + 7, y2 + 1), (0, 1))
        order = (right, left, above, below) if y2 - y1 > x2 - x1 else (above, below, right, left)
    # 每个方位再向外多挪 5、10 个单位，拥挤处也能找到空位。
    return [
        [_area(x + ux * step, y + uy * step + LINE * i, label, element) for i, label in enumerate(labels)]
        for step in (0, 5, 10)
        for (x, y), (ux, uy) in order
    ]


def place_text(plan, names=None, reset=False):
    """自动摆放关联文字：对压字、压符号、压导线的元件逐个试候选位置，取问题最少的。

    已经没有文字问题的计划原样返回；只动 names 指定的元件（默认全部有关元件）。
    reset 为真时先把这些元件的文字放到第一候选（横放在上方、竖放在右侧、探头名在右侧），让全图标注统一，再消除冲突。
    """
    plan = copy.deepcopy(plan)
    wanted = set(names) if names else None
    if reset:
        for element in plan['elements']:
            labels = element.get('textlinks', [])
            if labels and (wanted is None or element.get('name') in wanted):
                candidates = _text_candidates(element)
                if candidates:
                    for label, area in zip(labels, candidates[0]):
                        label['AREA'] = area
    problems = _text_problems(plan)
    if not problems:
        return plan
    for _ in range(2):
        spots = [tuple(f['at'][:2]) for f in problems if 'at' in f]
        for element in plan['elements']:
            labels = element.get('textlinks', [])
            if not labels or (wanted is not None and element.get('name') not in wanted):
                continue
            boxes = [text_box(element, label) for label in labels]
            if not any(abs(b[0] - x) < 30 and abs(b[1] - y) < 30 for b in boxes for x, y in spots):
                continue
            best = (len(problems), None)
            for areas in _text_candidates(element):
                saved = [label['AREA'] for label in labels]
                for label, area in zip(labels, areas):
                    label['AREA'] = area
                count = len(_text_problems(plan))
                for label, area in zip(labels, saved):
                    label['AREA'] = area
                if count < best[0]:
                    best = (count, areas)
                if count == 0:
                    break
            if best[1] is not None:
                for label, area in zip(labels, best[1]):
                    label['AREA'] = area
                problems = _text_problems(plan)
            if not problems:
                return plan
    if not reset:
        # 逐个挪不开时（唯一的空位正被别的文字占着），先把问题附近的、再把全部有关文字放回标准位置重摆，
        # 只在问题变少时采用。
        spots = [tuple(f['at'][:2]) for f in problems if 'at' in f]
        crowd = [
            element['name']
            for element in plan['elements']
            if element.get('textlinks')
            and (wanted is None or element.get('name') in wanted)
            and any(
                abs(b[0] - x) < 60 and abs(b[1] - y) < 60
                for b in (text_box(element, label) for label in element['textlinks'])
                for x, y in spots
            )
        ]
        for group in ([crowd] if crowd else []) + [names]:
            retry = place_text(plan, group, reset=True)
            left = _text_problems(retry)
            if len(left) < len(problems):
                plan, problems = retry, left
            if not problems:
                break
    return plan
