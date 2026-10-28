"""PSIM 建模计划的排版预检：导线、栅格、关联文字重叠、文字压线、仿真控制位置与参数写法。

PSIM 元件图形由原生库决定，计划里通常只写首端口；本工具只对已标定的常用元件估算符号范围。
关联文字按原生定位规则（起点 = AREA 水平中心 - FormatFactor）和 Arial 字宽估算实际位置。
结果用于原生创建前的快速把关，最终以原生导出和 review_emf_text.py 的审查为准。
"""

import argparse
import json
import math
from pathlib import Path
import re
import sys

from psim_plan import SYMBOLS, crosses, part_overlaps, ports as element_ports, symbol_box, symbol_parts, text_box

LIMITATIONS = (
    '只对已标定元件估算符号范围，文字位置按原生定位规则估算；端口与图形以本机原生库为准。'
    '通过预检不等于原生创建、求解或出图通过，仍须查看原生导出。'
)


TEXT_CLEARANCE = 2.0


def overlap(a, b, inset=0.0):
    return min(a[2], b[2]) - max(a[0], b[0]) > inset and min(a[3], b[3]) - max(a[1], b[1]) > inset


def gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return math.hypot(dx, dy)


def on_segment(p, seg):
    (x1, y1), (x2, y2) = seg
    if x1 == x2 == p[0]:
        return min(y1, y2) <= p[1] <= max(y1, y2)
    if y1 == y2 == p[1]:
        return min(x1, x2) <= p[0] <= max(x1, x2)
    return False


def hits_box(seg, box):
    (x1, y1), (x2, y2) = seg
    if x1 == x2:
        return box[0] < x1 < box[2] and min(y1, y2) < box[3] and max(y1, y2) > box[1]
    return box[1] < y1 < box[3] and min(x1, x2) < box[2] and max(x1, x2) > box[0]


def scientific(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value != 0 and not 1e-3 <= abs(value) < 1e6 or 'e' in repr(value)
    return bool(re.fullmatch(r'\s*-?\d+(?:\.\d+)?[eE][+-]?\d+\s*', str(value)))


def check_plan(plan, grid=10):
    elements = plan.get('elements')
    if not isinstance(elements, list) or not elements:
        raise ValueError('计划须含非空 elements 数组')
    findings = []

    def add(severity, code, message, hint, where=None, **extra):
        item = {'severity': severity, 'code': code, 'message': message, 'hint': hint}
        if where is not None:
            item['at'] = [round(v, 2) for v in where]
        item.update(extra)
        findings.append(item)

    wires, symbols, parts, texts, ports, clocks, uncalibrated = [], [], [], [], [], [], set()
    font_sizes = {}
    for e in elements:
        kind = str(e.get('type', '')).upper()
        name = e.get('name', '')
        attrs = e.get('attributes', {})
        if kind == 'WIRE':
            a = (float(attrs['X1']), float(attrs['Y1']))
            b = (float(attrs['X2']), float(attrs['Y2']))
            if a == b:
                add('error', 'ZERO_WIRE', '零长度导线', '删除该导线。', a)
            elif a[0] != b[0] and a[1] != b[1]:
                add('error', 'DIAGONAL_WIRE', '导线不是水平或竖直线段', '拆成正交线段。', a)
            else:
                wires.append((a, b))
            continue
        direction = float(attrs.get('DIRECTION', 0))
        if direction % 90:
            add(
                'warning',
                'ODD_DIRECTION',
                f'{name or kind} 的 DIRECTION={direction:g} 不是 90° 的整数倍',
                '使用 0、90、180、270。',
            )
        box = symbol_box(e)
        if kind == 'SIMCONTROL':
            if box:
                clocks.append(box)
        elif 'PORTS' in attrs:
            start = element_ports(e)[0]
            ports.extend(element_ports(e))
            if box:
                symbols.append((name or kind, box))
                parts.extend((name or kind, part) for part in symbol_parts(e))
            if kind not in SYMBOLS or SYMBOLS[kind].get('calibrated') is False:
                uncalibrated.add(kind)
            if any(abs(v / grid - round(v / grid)) > 1e-9 for v in start):
                add(
                    'warning',
                    'PORT_OFF_GRID',
                    f'{name or kind} 的首端口不在 {grid} 单位栅格上',
                    '端口与导线端点放在统一栅格上。',
                    start,
                )
        for label in e.get('textlinks', []):
            area = label.get('AREA')
            if not (isinstance(area, (list, tuple)) and len(area) == 4):
                add('error', 'TEXTLINK_AREA', f'{name} 的关联文字缺少 AREA[x1,y1,x2,y2]', '补齐 AREA。')
                continue
            box = tuple(float(v) for v in area)
            if box[2] <= box[0] or box[3] <= box[1]:
                add('error', 'TEXTLINK_AREA', f'{name} 的关联文字 AREA 无效', '使用 x1<x2、y1<y2 的矩形。')
                continue
            field = label.get('FieldName', '')
            size = abs(float(label.get('FontSize', -15)))
            font_sizes.setdefault(size, []).append(f'{name}.{field}')
            value = attrs.get(field)
            texts.append({'owner': name, 'field': field, 'area': box, 'box': text_box(e, label)})
            if field != 'Name' and value is not None and scientific(value):
                add(
                    'warning',
                    'VALUE_FORMAT',
                    f'{name}.{field}={value!r} 会显示为科学计数法或冗长小数',
                    '用 PSIM 后缀写法，例如 1u、100m、4.7k、2M。',
                    box[:2],
                )
    if len(font_sizes) > 1:
        add(
            'warning',
            'FONT_MIXED',
            '关联文字使用了多种字号',
            '位号和参数使用同一字号。',
            sizes={str(k): v for k, v in font_sizes.items()},
        )

    # ---- 导线 ----
    for i, (a, b) in enumerate(wires):
        for p in (a, b):
            if any(abs(v / grid - round(v / grid)) > 1e-9 for v in p):
                add('warning', 'WIRE_OFF_GRID', '导线端点不在栅格上', '端点放在统一栅格上。', p)
        for j in range(i + 1, len(wires)):
            c, d = wires[j]
            same_h = a[1] == b[1] == c[1] == d[1]
            same_v = a[0] == b[0] == c[0] == d[0]
            axis = 0 if same_h else 1 if same_v else None
            if axis is not None:
                lo = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
                hi = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
                if hi > lo:
                    add('warning', 'WIRE_OVERLAP', '两根导线共线重叠', '合并为一根导线，避免重复对象。', a)
    for i, (a, b) in enumerate(wires):
        for p in (a, b):
            connected = p in ports or any(j != i and on_segment(p, w) for j, w in enumerate(wires))
            if not connected:
                severity = 'info' if uncalibrated else 'warning'
                add(
                    severity,
                    'WIRE_END_UNMATCHED',
                    '导线端点没有落在已知端口或其他导线上',
                    '核对元件真实端口位置；未标定元件的端口须以原生导出为准。',
                    p,
                )
    crossings = 0
    for a, b in wires:
        for c, d in wires:
            if (
                a[1] == b[1]
                and c[0] == d[0]
                and min(a[0], b[0]) < c[0] < max(a[0], b[0])
                and min(c[1], d[1]) < a[1] < max(c[1], d[1])
            ):
                crossings += 1

    # ---- 文字 ----
    for i, t in enumerate(texts):
        for j in range(i + 1, len(texts)):
            if overlap(t['box'], texts[j]['box'], 0.5):
                add(
                    'error',
                    'TEXT_OVERLAP',
                    f'关联文字重叠：{t["owner"]}.{t["field"]} 与 {texts[j]["owner"]}.{texts[j]["field"]}',
                    '错开 AREA，同一元件的位号和参数上下排列；或用编辑操作 {"op": "place_text"} 自动摆放。',
                    t['box'][:2],
                )
        # 同一段文字压到同一个元件只报一次（元件按引线、主体分块判断）。
        touched = list(dict.fromkeys(name for name, part in parts if part_overlaps(part, t['box'], 0.5)))
        for name in touched:
            add(
                'warning',
                'TEXT_ON_SYMBOL',
                f'{t["owner"]}.{t["field"]} 的文字压到 {name} 的符号',
                '移动 AREA（文字起点 = AREA 水平中心 - FormatFactor），与图形留至少 2 个单位；'
                '或用编辑操作 {"op": "place_text"} 自动摆放。',
                t['box'][:2],
            )
        for clock in clocks:
            if overlap(t['box'], clock, 0.5):
                add(
                    'warning',
                    'TEXT_ON_SYMBOL',
                    f'{t["owner"]}.{t["field"]} 的文字压到仿真控制图标',
                    '把仿真控制移到图纸角落。',
                    t['box'][:2],
                )
        crossed = next((seg for seg in wires if hits_box(seg, t['box'])), None)
        if crossed:
            add(
                'warning',
                'TEXT_ON_WIRE',
                f'{t["owner"]}.{t["field"]} 的文字被导线穿过',
                '文字放在导线旁的空白处，或用编辑操作 {"op": "place_text"} 自动摆放。',
                t['box'][:2],
            )
        elif not touched:
            # 排版规则：文字与导线、符号至少留 2 个单位（留 0.1 的取整余量）。
            margin = TEXT_CLEARANCE - 0.1
            grown = (t['box'][0] - margin, t['box'][1] - margin, t['box'][2] + margin, t['box'][3] + margin)
            near = ['导线'] if any(hits_box(seg, grown) for seg in wires) else []
            near += list(dict.fromkeys(name for name, part in parts if part_overlaps(part, t['box'], -margin)))
            if near:
                add(
                    'warning',
                    'TEXT_NEAR_LINE',
                    f'{t["owner"]}.{t["field"]} 的文字贴着{"、".join(near)}，间距不到 {TEXT_CLEARANCE:g} 个单位',
                    '文字与导线、符号至少留 2 个单位；可用编辑操作 {"op": "place_text"} 自动摆放。',
                    t['box'][:2],
                )
    for clock in clocks:
        near = [name for name, box in symbols if gap(clock, box) < 20]
        near += [f'{t["owner"]}.{t["field"]}' for t in texts if gap(clock, t['box']) < 10]
        if near:
            add(
                'warning',
                'SIMCONTROL_CROWDED',
                '仿真控制图标离电路太近：' + '、'.join(near[:6]),
                '放到图纸角落，与电路图形至少相距 20 个单位。',
                clock[:2],
            )
    for seg in wires:
        for name, box in symbols + [('SIMCONTROL', c) for c in clocks]:
            if crosses(seg, box):
                add('warning', 'WIRE_THROUGH_SYMBOL', f'导线穿过 {name} 的符号', '改走线，从端口外侧接入。', seg[0])
    for a in range(len(symbols)):
        for b in range(a + 1, len(symbols)):
            if overlap(symbols[a][1], symbols[b][1], 2):
                add(
                    'warning',
                    'SYMBOL_OVERLAP',
                    f'{symbols[a][0]} 与 {symbols[b][0]} 的符号重叠',
                    '拉开元件。',
                    symbols[a][1][:2],
                )

    boxes = [box for _, box in symbols] + clocks + [t['box'] for t in texts]
    boxes += [(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for a, b in wires]
    metrics = {
        'elements': len(elements),
        'wires': len(wires),
        'textlinks': len(texts),
        'crossings': crossings,
        'uncalibrated_types': sorted(uncalibrated),
    }
    if boxes:
        metrics['content_box'] = [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ]
    order = {'error': 0, 'warning': 1, 'info': 2}
    findings.sort(key=lambda f: order[f['severity']])
    summary = {s + 's': sum(f['severity'] == s for f in findings) for s in order}
    summary['passed'] = summary['errors'] == 0
    return {'summary': summary, 'metrics': metrics, 'findings': findings, 'limitations': LIMITATIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', type=Path, help='native_psim.py create 使用的 JSON 计划')
    parser.add_argument('--grid', type=float, default=10.0)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true', help='warning 也视为未通过')
    args = parser.parse_args()
    try:
        if args.grid <= 0:
            raise ValueError('grid 须为正数')
        if args.output and args.output.resolve() == args.plan.resolve():
            raise ValueError('输出路径不能覆盖计划')
        result = check_plan(json.loads(args.plan.read_text(encoding='utf-8-sig')), args.grid)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + '\n', encoding='utf-8')
        print(text)
        failed = result['summary']['errors'] or (args.strict and result['summary']['warnings'])
        return 1 if failed else 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
