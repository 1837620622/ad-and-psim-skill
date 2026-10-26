"""PSIM 建模计划：元件几何、端口、关联文字和编辑操作。坐标 y 向下。

SYMBOLS 中的几何按 PSIM 2026 原生导出标定（DIRECTION=0，相对首端口）；其余元件只知道首端口。
"""

import copy
import re

SYMBOLS = {
    'R': {'ports': [(0, 0), (50, 0)], 'box': (0, -7, 50, 7)},
    'C': {'ports': [(0, 0), (50, 0)], 'box': (0, -8, 50, 8)},
    'L': {'ports': [(0, 0), (50, 0)], 'box': (0, -8, 50, 2), 'calibrated': False},
    'VDC': {'ports': [(0, 0), (0, 50)], 'box': (-11, 0, 11, 50)},
    'VSIN': {'ports': [(0, 0), (0, 50)], 'box': (-11, 0, 11, 50), 'calibrated': False},
    'VP': {'ports': [(0, 0)], 'box': (-11, -31, 11, 0)},
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
            dx, dy = op.get('dx', 0), op.get('dy', 0)
            if 'to' in op:
                current = origin(element)
                dx, dy = op['to'][0] - current[0], op['to'][1] - current[1]
            attached = set(ports(element))
            _shift_element(element, dx, dy)
            obstacles = [box for box in map(symbol_box, elements) if box]
            moved = []
            for wire in [e for e in elements if kind(e) == 'WIRE']:
                a, b = wire_points(wire)
                if a in attached or b in attached:
                    a = (a[0] + dx, a[1] + dy) if a in attached else a
                    b = (b[0] + dx, b[1] + dy) if b in attached else b
                    elements.remove(wire)
                    moved += square(a, b, obstacles)
            elements.extend(moved)
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
        else:
            raise ValueError(f'未知编辑操作：{action!r}')
    return plan
