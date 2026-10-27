"""AD 建模计划的排版预检：栅格、悬空线端、隐式连接、预测网表、文字碰撞、穿件导线与画面密度。

在调用 AD 之前快速把关，结果与模型无关、可重复。文字尺寸按 Times New Roman 度量与原生导出
标定估算，预览图是草图而不是原生导出；最终仍以 AD 编译、原生出图和 review_emf_text.py 为准。
"""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys

# Times New Roman（与 Liberation Serif 度量一致）ASCII 32..126 的字宽，单位 1/1000 em。
TIMES = (
    250,
    333,
    408,
    500,
    500,
    833,
    778,
    180,
    333,
    333,
    500,
    564,
    250,
    333,
    250,
    278,
    500,
    500,
    500,
    500,
    500,
    500,
    500,
    500,
    500,
    500,
    278,
    278,
    564,
    564,
    564,
    444,
    921,
    722,
    667,
    667,
    722,
    611,
    556,
    722,
    722,
    333,
    389,
    722,
    611,
    889,
    722,
    722,
    556,
    722,
    667,
    556,
    611,
    722,
    722,
    944,
    722,
    722,
    611,
    333,
    278,
    333,
    469,
    500,
    333,
    444,
    500,
    444,
    500,
    444,
    333,
    500,
    500,
    278,
    278,
    500,
    278,
    778,
    500,
    500,
    500,
    500,
    333,
    389,
    278,
    500,
    500,
    722,
    500,
    500,
    444,
    480,
    200,
    480,
    541,
)
# 原生 EMF 标定：字号每 pt 约 0.85 个 10mil 单位的 em，字格高度约 1 个单位。
EM_PER_PT = 0.85
CELL_PER_PT = 1.0
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
PASSIVES = {'R', 'C', 'L', 'Y'}
GROUND_STYLES = {'4', '5', '6'}
DESCENDERS = set('gjpqy(),;_[]{}|')
LIMITATIONS = (
    '文字字框按 Times New Roman 度量估算；连接按 AD 规则（端点、热端落在导线上、同名标号）'
    '预测。通过预检不等于原生编译通过或图面已验收，仍须原生编译、原生出图和逐区审图。'
)


def text_width(text, pt):
    em = EM_PER_PT * pt
    total = 0
    for ch in text:
        code = ord(ch)
        total += TIMES[code - 32] if 32 <= code < 127 else 1000
    return total / 1000 * em


def rotate_box(box, x, y, orientation):
    """把以锚点为原点的局部框按 90° 步进逆时针旋转并平移到锚点。"""
    x1, y1, x2, y2 = box
    corners = [(x1, y1), (x2, y2)]
    turn = int(orientation) % 4
    for _ in range(turn):
        corners = [(-v, u) for u, v in corners]
    xs = [u for u, _ in corners]
    ys = [v for _, v in corners]
    return (x + min(xs), y + min(ys), x + max(xs), y + max(ys))


def text_boxes(text, x, y, pt, orientation=0, justification=0):
    """返回 (字格框, 字形框)；锚点为左下角，justification 0..8 为下/中/上 × 左/中/右。"""
    w = text_width(text, pt)
    h = CELL_PER_PT * pt
    jx = (0, 0.5, 1)[justification % 3]
    jy = (0, 0.5, 1)[min(justification // 3, 2)]
    left, bottom = -jx * w, -jy * h
    low = 0.06 if DESCENDERS & set(text) or any(ord(c) > 0x2E80 for c in text) else 0.22
    cell = rotate_box((left, bottom, left + w, bottom + h), x, y, orientation)
    ink = rotate_box((left, bottom + low * h, left + w, bottom + 0.81 * h), x, y, orientation)
    return cell, ink


def overlap(a, b, inset=0.0):
    return min(a[2], b[2]) - max(a[0], b[0]) > inset and min(a[3], b[3]) - max(a[1], b[1]) > inset


def shrink(box, d):
    return (box[0] + d, box[1] + d, box[2] - d, box[3] - d)


def segment_hits_box(seg, box):
    """线段与开区间矩形相交（Liang-Barsky 裁剪）。"""
    (x1, y1), (x2, y2) = seg
    if box[2] <= box[0] or box[3] <= box[1]:
        return False
    dx, dy = x2 - x1, y2 - y1
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x1 - box[0]), (dx, box[2] - x1), (-dy, y1 - box[1]), (dy, box[3] - y1)):
        if p == 0:
            if q <= 0:
                return False
            continue
        t = q / p
        if p < 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo >= hi:
            return False
    return True


def on_segment(point, seg):
    (x1, y1), (x2, y2) = seg
    px, py = point
    if x1 == x2 == px:
        return min(y1, y2) <= py <= max(y1, y2)
    if y1 == y2 == py:
        return min(x1, x2) <= px <= max(x1, x2)
    return False


def interior(point, seg):
    return on_segment(point, seg) and point not in seg


def off_grid(point, grid):
    return any(abs(v / grid - round(v / grid)) > 1e-9 for v in point)


def num(record, key, default=0.0):
    try:
        return float(record.get(key, default))
    except ValueError:
        return default


class Finder:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def parse(records):
    sheet = records[1] if len(records) > 1 else {}
    sizes = {int(k[4:]): float(v) for k, v in sheet.items() if re.fullmatch(r'SIZE\d+', k)}
    system_font = int(num(sheet, 'SYSTEMFONT', 1))

    def pt(record):
        return sizes.get(int(num(record, 'FONTID', system_font)), 10.0)

    parts, pins, wires, labels, ports, junctions, texts, borders = {}, [], [], [], [], [], [], []
    for index, r in enumerate(records):
        if r.get('RECORD') == '1':
            parts[index] = {
                'index': index,
                'lib': r.get('LIBREFERENCE', ''),
                'ref': None,
                'rects': [],
                'lines': [],
                'pins': [],
                'texts': [],
            }
    for r in records:
        kind = r.get('RECORD')
        owner = parts.get(int(r['OWNERINDEX']) + 1) if 'OWNERINDEX' in r else None
        location = (num(r, 'LOCATION.X'), num(r, 'LOCATION.Y'))
        if kind == '2' and owner is not None:
            flags = int(num(r, 'PINCONGLOMERATE'))
            direction = flags & 3
            length = num(r, 'PINLENGTH')
            dx, dy = DIRS[direction]
            pin = {
                'owner': owner,
                'number': r.get('DESIGNATOR', ''),
                'name': r.get('NAME', ''),
                'base': location,
                'hot': (location[0] + dx * length, location[1] + dy * length),
                'direction': direction,
                'length': length,
                'show_name': bool(flags & 8),
                'show_number': bool(flags & 16),
            }
            owner['pins'].append(pin)
            pins.append(pin)
        elif kind == '14':
            box = (location[0], location[1], num(r, 'CORNER.X'), num(r, 'CORNER.Y'))
            box = (min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3]))
            (owner['rects'] if owner else borders).append(box)
        elif kind == '6' and owner is not None:
            count = int(num(r, 'LOCATIONCOUNT'))
            points = [(num(r, f'X{i}'), num(r, f'Y{i}')) for i in range(1, count + 1)]
            owner['lines'].extend(zip(points, points[1:]))
        elif kind == '27':
            count = int(num(r, 'LOCATIONCOUNT'))
            points = [(num(r, f'X{i}'), num(r, f'Y{i}')) for i in range(1, count + 1)]
            wires.extend((a, b) for a, b in zip(points, points[1:]) if a != b)
        elif kind == '25':
            labels.append(
                {'name': r.get('TEXT', ''), 'at': location, 'pt': pt(r), 'orientation': int(num(r, 'ORIENTATION'))}
            )
        elif kind == '17':
            ports.append(
                {
                    'name': r.get('TEXT', ''),
                    'at': location,
                    'style': r.get('STYLE', '2'),
                    'orientation': int(num(r, 'ORIENTATION')),
                    'pt': pt(r),
                    'show': r.get('SHOWNETNAME', 'T') == 'T',
                }
            )
        elif kind == '29':
            junctions.append(location)
        elif kind == '4':
            texts.append(
                {
                    'text': r.get('TEXT', ''),
                    'at': location,
                    'pt': pt(r),
                    'kind': 'text',
                    'owner': None,
                    'orientation': int(num(r, 'ORIENTATION')),
                    'justification': int(num(r, 'JUSTIFICATION')),
                }
            )
        elif kind in ('34', '41') and owner is not None:
            if kind == '34':
                owner['ref'] = r.get('TEXT')
            if r.get('ISHIDDEN') == 'T' or (kind == '41' and r.get('NAME') != 'Comment'):
                continue
            item = {
                'text': r.get('TEXT', ''),
                'at': location,
                'pt': pt(r),
                'owner': owner,
                'kind': 'designator' if kind == '34' else 'comment',
                'orientation': int(num(r, 'ORIENTATION')),
                'justification': int(num(r, 'JUSTIFICATION')),
            }
            owner['texts'].append(item)
            texts.append(item)
    border = (
        max(borders, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        if borders
        else (0.0, 0.0, num(sheet, 'CUSTOMX', 1000), num(sheet, 'CUSTOMY', 800))
    )
    for part in parts.values():
        part['passive'] = part['lib'] in PASSIVES
        xs, ys = [], []
        for box in part['rects']:
            xs += [box[0], box[2]]
            ys += [box[1], box[3]]
        for a, b in part['lines']:
            xs += [a[0], b[0]]
            ys += [a[1], b[1]]
        if not xs:
            for pin in part['pins']:
                xs.append(pin['base'][0])
                ys.append(pin['base'][1])
        part['body'] = (min(xs), min(ys), max(xs), max(ys)) if xs else None
    return {
        'parts': parts,
        'pins': pins,
        'wires': wires,
        'labels': labels,
        'ports': ports,
        'junctions': junctions,
        'texts': texts,
        'border': border,
        'system_pt': sizes.get(system_font, 10.0),
    }


def pin_texts(pin, system_pt):
    """近似 AD 的引脚名（框内、居中于引脚线）与引脚号（引脚线上方）位置。"""
    items = []
    (bx, by), d, h = pin['base'], pin['direction'], CELL_PER_PT * system_pt
    if pin['show_name'] and pin['name'].strip():
        w = text_width(pin['name'], system_pt)
        gap, half = 7.0, 0.3 * h
        box = {
            0: (bx - gap - w, by - half, bx - gap, by + half),
            2: (bx + gap, by - half, bx + gap + w, by + half),
            1: (bx - half, by - gap - w, bx + half, by - gap),
            3: (bx - half, by + gap, bx + half, by + gap + w),
        }[d]
        items.append(
            {
                'text': pin['name'],
                'ink': box,
                'cell': box,
                'kind': 'pin_name',
                'owner': pin['owner'],
                'orientation': d % 2,
                'pt': system_pt,
            }
        )
    if pin['show_number'] and pin['number'].strip():
        # AD 的引脚号从器件边沿向外偏 9 个单位对齐。
        w = text_width(pin['number'], system_pt)
        start = {0: bx + 9, 2: bx - 9 - w, 1: by + 9, 3: by - 9 - w}[d]
        if d in (0, 2):
            box = (start, by + 0.24 * h, start + w, by + 0.77 * h)
        else:
            box = (bx - 0.77 * h, start, bx - 0.24 * h, start + w)
        items.append(
            {
                'text': pin['number'],
                'ink': box,
                'cell': box,
                'kind': 'pin_number',
                'owner': pin['owner'],
                'orientation': d % 2,
                'pt': system_pt,
            }
        )
    return items


def port_geometry(port):
    """电源/地符号与名称的近似范围；地符号朝下约 18 个单位，名称在符号外侧居中。"""
    x, y = port['at']
    reach = 18.0 if port['style'] in GROUND_STYLES else 10.0
    symbol = rotate_box((-10, 0, 10, reach), x, y, (port['orientation'] - 1) % 4)
    texts = []
    if port['show'] and port['name']:
        w, h = text_width(port['name'], port['pt']), CELL_PER_PT * port['pt']
        local = (-w / 2, reach + 1, w / 2, reach + 1 + h)
        cell = rotate_box(local, x, y, (port['orientation'] - 1) % 4)
        ink = rotate_box(
            (-w / 2, reach + 1 + 0.22 * h, w / 2, reach + 1 + 0.81 * h), x, y, (port['orientation'] - 1) % 4
        )
        if port['orientation'] % 2 == 0:
            # 左右朝向时 AD 保持名称水平。
            cx, cy = (cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2
            cell = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            ink = (cx - w / 2, cy - 0.3 * h, cx + w / 2, cy + 0.3 * h)
        texts.append(
            {
                'text': port['name'],
                'cell': cell,
                'ink': ink,
                'kind': 'power',
                'owner': None,
                'orientation': 0,
                'pt': port['pt'],
            }
        )
    return symbol, texts


def check_records(records, pin_map=None, grid=10):
    model = parse(records)
    parts, pins, wires = model['parts'], model['pins'], model['wires']
    labels, ports, junctions = model['labels'], model['ports'], model['junctions']
    findings = []

    def add(severity, code, message, hint, where=None, **extra):
        item = {'severity': severity, 'code': code, 'message': message, 'hint': hint}
        if where is not None:
            item['at'] = [round(v, 2) for v in where]
        item.update(extra)
        findings.append(item)

    def name(pin):
        return f'{pin["owner"]["ref"]}.{pin["number"]}'

    # ---- 栅格 ----
    for pin in pins:
        if off_grid(pin['hot'], grid):
            add(
                'error',
                'PIN_OFF_GRID',
                f'{name(pin)} 的热端不在 {grid} 单位栅格上',
                '调整器件位置或引脚长度，使热端落在栅格；否则在 AD 中难以吸附接线。',
                pin['hot'],
            )
    for seg in wires:
        for p in seg:
            if off_grid(p, grid):
                add('error', 'WIRE_OFF_GRID', '导线端点不在栅格上', '导线端点与折点放在栅格上。', p)
    for item, kind in [(x, '网络标号') for x in labels] + [(x, '电源端口') for x in ports]:
        if off_grid(item['at'], grid):
            add(
                'warning',
                'ANCHOR_OFF_GRID',
                f'{kind} {item["name"]} 的锚点不在栅格上',
                '标号和电源端口锚点放在栅格与导线上。',
                item['at'],
            )

    # ---- 连接（按 AD 规则）----
    horizontal, vertical = defaultdict(list), defaultdict(list)
    for i, seg in enumerate(wires):
        (x1, y1), (x2, y2) = seg
        if y1 == y2:
            horizontal[y1].append(i)
        if x1 == x2:
            vertical[x1].append(i)

    def segments_at(point):
        hits = {i for i in horizontal.get(point[1], []) if on_segment(point, wires[i])}
        hits |= {i for i in vertical.get(point[0], []) if on_segment(point, wires[i])}
        return hits

    finder = Finder()
    hot_points = defaultdict(list)
    for k, pin in enumerate(pins):
        hot_points[pin['hot']].append(k)
    for i, seg in enumerate(wires):
        finder.find(('w', i))
        for p in seg:
            for j in segments_at(p):
                finder.union(('w', i), ('w', j))
    for point in junctions:
        hits = sorted(segments_at(point))
        for j in hits[1:]:
            finder.union(('w', hits[0]), ('w', j))
    attached = set()
    for point, members in hot_points.items():
        # 引脚本身算一个分支；再有两根导线从热端引出就是落在引脚上的 T 形连接。
        leaving = {other for j in segments_at(point) for other in wires[j] if point in wires[j] and other != point}
        if len(leaving) >= 2:
            add(
                'info' if pin_map else 'warning',
                'PIN_TEE',
                f'导线从 {name(pins[members[0]])} 的热端两侧穿过，形成 T 形连接',
                '确认这是预期连接；常规画法是从引脚引出短线再接到干线。',
                point,
            )
        for k in members:
            for j in segments_at(point):
                finder.union(('p', k), ('w', j))
                attached.add(k)
                if interior(point, wires[j]):
                    add(
                        'warning',
                        'PIN_ON_WIRE_MIDDLE',
                        f'{name(pins[k])} 的热端落在导线中段，AD 会自动连接',
                        '确认这是预期连接；否则移开器件或改走线，避免隐式短接。',
                        point,
                    )
            for m in members:
                if m != k:
                    finder.union(('p', k), ('p', m))
                    attached.add(k)
    names = defaultdict(list)
    for kind, items in (('label', labels), ('port', ports)):
        for n, item in enumerate(items):
            key = (kind, n)
            finder.find(key)
            names[item['name']].append(key)
            hits = segments_at(item['at'])
            for j in hits:
                finder.union(key, ('w', j))
            for k in hot_points.get(item['at'], []):
                finder.union(key, ('p', k))
                attached.add(k)
            if not hits and item['at'] not in hot_points:
                add(
                    'error',
                    'LABEL_FLOATING' if kind == 'label' else 'PORT_FLOATING',
                    f'{"网络标号" if kind == "label" else "电源端口"} {item["name"]} 的锚点没有落在导线或引脚热端上',
                    '把锚点移到导线上；文字看起来贴近不等于电气连接。',
                    item['at'],
                )
    for members in names.values():
        for key in members[1:]:
            finder.union(members[0], key)
    endpoints = {p for item in labels + ports for p in [item['at']]} | set(hot_points)
    for i, seg in enumerate(wires):
        for p in seg:
            if p in endpoints or p in junctions:
                continue
            if any(j != i for j in segments_at(p)):
                continue
            add(
                'error',
                'DANGLING_WIRE',
                '导线端点悬空，没有接到引脚、导线、标号或电源端口',
                '延长到真实热端或删除多余线段。',
                p,
            )
    for k, pin in enumerate(pins):
        if k in attached:
            continue
        if pin['owner']['passive']:
            add('error', 'PASSIVE_PIN_UNCONNECTED', f'{name(pin)} 未连接', '无源件两端都应接入电路。', pin['hot'])
        else:
            add(
                'warning',
                'PIN_UNCONNECTED',
                f'{name(pin)} 未连接',
                '确认是否为 NC；需要时连线或在原生工程中放置 No ERC 标记。',
                pin['hot'],
            )
    groups = defaultdict(list)
    for k in sorted(attached):
        groups[finder.find(('p', k))].append(k)
    group_names = {}
    for nm, members in sorted(names.items()):
        group_names.setdefault(finder.find(members[0]), nm)
    predicted = {}
    netlist = []
    for n, (root, members) in enumerate(sorted(groups.items(), key=lambda kv: min(name(pins[k]) for k in kv[1])), 1):
        net = group_names.get(root, f'N{n:03d}')
        for k in members:
            predicted[name(pins[k])] = net
            netlist.append(f'{net}|{pins[k]["owner"]["ref"]}|{pins[k]["number"]}')
    topology = None
    if pin_map:
        from compare_pin_nets import compare

        topology = compare(pin_map, predicted)
        if not topology['match']:
            add(
                'error',
                'TOPOLOGY_MISMATCH',
                '按 AD 规则预测的连接与 pin_map 不一致',
                '查看 topology 中的 missing/added/changed 引脚，修正走线或 pin_map 的设计意图。',
                missing=topology['missing_pins'],
                added=topology['added_pins'],
                changed=topology['changed_pins'][:20],
            )

    # ---- 走线形态 ----
    crossings = []
    for y, hs in horizontal.items():
        for i in hs:
            (ax, _), (bx, _) = wires[i]
            for x, vs in vertical.items():
                if not min(ax, bx) < x < max(ax, bx):
                    continue
                for j in vs:
                    (_, cy), (_, dy) = wires[j]
                    if min(cy, dy) < y < max(cy, dy) and (x, y) not in junctions:
                        crossings.append((x, y))
    if crossings:
        add(
            'info',
            'WIRE_CROSSINGS',
            f'{len(crossings)} 处导线交叉但不连接',
            '减少交叉可提高可读性；必要的交叉保持正交。',
            points=[list(p) for p in crossings[:20]],
        )
    vertices = defaultdict(set)
    for seg in wires:
        a, b = seg
        for p, q in ((a, b), (b, a)):
            vertices[p].add(
                (
                    int(math.copysign(1, q[0] - p[0])) if q[0] != p[0] else 0,
                    int(math.copysign(1, q[1] - p[1])) if q[1] != p[1] else 0,
                )
            )
    for p, dirs in vertices.items():
        if len(dirs) >= 4:
            add(
                'warning',
                'FOUR_WAY_JUNCTION',
                '四向连接点',
                '错开成两个相距至少一个栅格的 T 形连接，避免与交叉混淆。',
                p,
            )
    for seg in wires:
        length = abs(seg[0][0] - seg[1][0]) + abs(seg[0][1] - seg[1][1])
        if 0 < length < grid:
            add('warning', 'SHORT_JOG', f'导线段只有 {length:g} 个单位', '对齐两端热端，去掉小台阶。', seg[0])
    bodies = [(part, part['body']) for part in parts.values() if part['body']]
    for seg in wires:
        for part, body in bodies:
            if segment_hits_box(seg, shrink(body, 0.5)):
                add(
                    'warning', 'WIRE_THROUGH_BODY', f'导线穿过 {part["ref"]} 的符号', '绕开器件或调整器件位置。', seg[0]
                )
        for pin in pins:
            line = (pin['base'], pin['hot'])
            if pin['hot'] in seg or interior(pin['hot'], seg):
                continue
            pin_box = (
                min(line[0][0], line[1][0]) - 0.5,
                min(line[0][1], line[1][1]) - 0.5,
                max(line[0][0], line[1][0]) + 0.5,
                max(line[0][1], line[1][1]) + 0.5,
            )
            if segment_hits_box(seg, pin_box):
                add(
                    'warning',
                    'WIRE_OVER_PIN',
                    f'导线压过 {name(pin)} 的引脚线',
                    '导线只接到热端，不沿引脚或横穿引脚。',
                    seg[0],
                )
    for a in range(len(bodies)):
        for b in range(a + 1, len(bodies)):
            if overlap(bodies[a][1], bodies[b][1], 0.5):
                add(
                    'error',
                    'PART_OVERLAP',
                    f'{bodies[a][0]["ref"]} 与 {bodies[b][0]["ref"]} 的符号重叠',
                    '拉开器件，保留文字与接线空间。',
                    bodies[a][1][:2],
                )
    for pin in pins:
        for part, body in bodies:
            if part is pin['owner']:
                continue
            if segment_hits_box((pin['base'], pin['hot']), shrink(body, 0.5)):
                add('error', 'PIN_INTO_PART', f'{name(pin)} 伸入 {part["ref"]} 的符号', '拉开器件。', pin['hot'])

    # ---- 文字 ----
    texts = []
    for item in model['texts']:
        cell, ink = text_boxes(item['text'], *item['at'], item['pt'], item['orientation'], item['justification'])
        texts.append(dict(item, cell=cell, ink=ink))
    for label in labels:
        cell, ink = text_boxes(label['name'], *label['at'], label['pt'], label['orientation'])
        texts.append(
            {
                'text': label['name'],
                'cell': cell,
                'ink': ink,
                'kind': 'label',
                'owner': None,
                'orientation': label['orientation'],
                'pt': label['pt'],
            }
        )
    port_symbols = []
    for port in ports:
        symbol, items = port_geometry(port)
        port_symbols.append((port, symbol))
        texts.extend(items)
    for pin in pins:
        texts.extend(pin_texts(pin, model['system_pt']))
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            if overlap(a['ink'], b['ink'], 0.3):
                add(
                    'warning',
                    'TEXT_OVERLAP',
                    f'文字重叠：{a["text"]!r} 与 {b["text"]!r}',
                    '移开其中一个文字，保持至少一个字高的一半作为间距。',
                    a['ink'][:2],
                )
    obstacles = [(seg, 'wire', None) for seg in wires]
    obstacles += [((pin['base'], pin['hot']), 'pin', pin['owner']) for pin in pins]
    for part in parts.values():
        for box in part['rects']:
            x1, y1, x2, y2 = box
            obstacles += [
                (edge, 'body', part)
                for edge in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1)))
            ]
        obstacles += [(line, 'body', part) for line in part['lines']]
    for _, symbol in port_symbols:
        obstacles.append(((symbol[:2], symbol[2:]), 'power', None))
    for item in texts:
        box = shrink(item['ink'], 0.3)
        hits = []
        for seg, kind, _ in obstacles:
            if kind == 'power':
                if overlap(box, (seg[0][0], seg[0][1], seg[1][0], seg[1][1])):
                    hits.append('电源符号')
            elif segment_hits_box(seg, box):
                hits.append({'wire': '导线', 'pin': '引脚', 'body': '器件图形'}[kind])
        if hits:
            add(
                'warning',
                'TEXT_ON_GRAPHICS',
                f'文字 {item["text"]!r} 压在{"、".join(sorted(set(hits)))}上',
                '把文字移到空白处：位号/参数放在器件外侧，网络名放在导线上方。',
                item['ink'][:2],
            )
        for part, body in bodies:
            if part is item.get('owner') or part['passive']:
                continue
            if overlap(box, body):
                add(
                    'warning',
                    'TEXT_ON_PART',
                    f'文字 {item["text"]!r} 落在 {part["ref"]} 的器件框内',
                    '文字只放在所属器件附近的空白处。',
                    item['ink'][:2],
                )

    # ---- 图框与密度 ----
    border = model['border']
    extents = []
    for seg in wires:
        extents.append(
            (min(seg[0][0], seg[1][0]), min(seg[0][1], seg[1][1]), max(seg[0][0], seg[1][0]), max(seg[0][1], seg[1][1]))
        )
    extents += [body for _, body in bodies]
    extents += [
        (
            min(p['base'][0], p['hot'][0]),
            min(p['base'][1], p['hot'][1]),
            max(p['base'][0], p['hot'][0]),
            max(p['base'][1], p['hot'][1]),
        )
        for p in pins
    ]
    extents += [symbol for _, symbol in port_symbols]
    extents += [item['cell'] for item in texts]
    metrics = {
        'parts': len(parts),
        'pins': len(pins),
        'wire_segments': len(wires),
        'texts': len(texts),
        'crossings': len(crossings),
        'border': list(border),
    }
    if extents:
        content = (
            min(e[0] for e in extents),
            min(e[1] for e in extents),
            max(e[2] for e in extents),
            max(e[3] for e in extents),
        )
        for e in extents:
            if e[0] < border[0] or e[1] < border[1] or e[2] > border[2] or e[3] > border[3]:
                add('error', 'OUTSIDE_BORDER', '图元或文字超出图框', '移入图框或放大画布。', e[:2])
                break
        area = max((border[2] - border[0]) * (border[3] - border[1]), 1e-9)
        fill = (content[2] - content[0]) * (content[3] - content[1]) / area
        margins = [content[0] - border[0], content[1] - border[1], border[2] - content[2], border[3] - content[3]]
        metrics.update(
            content_box=[round(v, 1) for v in content],
            fill_ratio=round(fill, 3),
            margins_left_bottom_right_top=[round(v, 1) for v in margins],
        )
        if fill < 0.3 and len(parts) > 1:
            margin = 4 * grid
            width = math.ceil((content[2] - content[0] + 2 * margin) / grid) * grid + 2 * (border[0])
            height = math.ceil((content[3] - content[1] + 2 * margin) / grid) * grid + 2 * (border[1])
            add(
                'warning',
                'SPARSE_SHEET',
                f'内容只占图框面积的 {fill:.0%}，图面偏空',
                '缩小 canvas 或按功能区收紧间距；大块空白会显得松散。',
                suggested_canvas=[width, height],
                suggested_shift=[
                    round((border[0] + margin - content[0]) / grid) * grid,
                    round((border[1] + margin - content[1]) / grid) * grid,
                ],
            )
        if extents and min(margins) >= 0 and max(margins) > 3 * max(min(margins), grid) and fill >= 0.3:
            add(
                'info',
                'UNBALANCED_MARGINS',
                '四周留白明显不均',
                '整体平移内容，使左右、上下留白接近。',
                margins=[round(v, 1) for v in margins],
            )

    # ---- 文本内容与符号约定 ----
    values = []
    for part in parts.values():
        ref = part['ref'] or ''
        if ref and not re.fullmatch(r'[A-Z]{1,4}\d+[A-Z]?', ref):
            add('warning', 'DESIGNATOR_FORMAT', f'位号 {ref!r} 不符合常规格式', '使用 R1、C12、U3、J1 这类字母加序号。')
        for item in part['texts']:
            if item['kind'] == 'comment' and part['passive']:
                values.append((ref, item['text']))
    for ref, value in values:
        if re.search(r'\d[eE][+-]?\d', value):
            add(
                'warning',
                'VALUE_FORMAT',
                f'{ref} 的参数 {value!r} 使用科学计数法',
                '写成 1uF、4.7k、100nF 这类工程写法。',
            )
        elif re.fullmatch(r'0\.\d+\s*[kmunp]?[FHΩ]?', value):
            add(
                'info',
                'VALUE_FORMAT',
                f'{ref} 的参数 {value!r} 以 0. 开头',
                '可换用下一级前缀，例如 0.1uF 写作 100nF；全图保持同一写法。',
            )
    resistor_suffix = {m.group(1) for ref, v in values if ref.startswith('R') for m in [re.search(r'\d([kK])', v)] if m}
    if len(resistor_suffix) > 1:
        add('warning', 'VALUE_STYLE_MIXED', '电阻值同时使用 k 与 K', '全图统一写法，常用小写 k。')
    for record in records:
        for key, value in record.items():
            try:
                str(value).encode('gbk')
            except UnicodeEncodeError:
                add(
                    'error',
                    'TEXT_ENCODING',
                    f'{key}={value!r} 含有 GBK 无法写入的字符',
                    '把 µ 写成 u，或改用 GBK 支持的字符。',
                )
    part_pt = [item['pt'] for item in model['texts'] if item['kind'] in ('designator', 'comment')]
    for item in model['texts']:
        if item['kind'] == 'text' and part_pt and item['pt'] >= 1.3 * max(part_pt):
            add(
                'warning',
                'FLOATING_TITLE',
                f'图面中的大号文字 {item["text"]!r}',
                '标题写进图签或删除；图面只保留必要说明，与器件文字同一字体。',
                item['at'],
            )
    for port in ports:
        expected = 3 if port['style'] in GROUND_STYLES else 1
        if port['orientation'] != expected:
            add(
                'warning',
                'POWER_ORIENTATION',
                f'{port["name"]} 符号朝向不常规',
                '地符号朝下（orientation 3），电源符号朝上（orientation 1）。',
                port['at'],
            )

    order = {'error': 0, 'warning': 1, 'info': 2}
    findings.sort(key=lambda f: order[f['severity']])
    summary = {s + 's': sum(f['severity'] == s for f in findings) for s in order}
    summary['passed'] = summary['errors'] == 0
    result = {
        'summary': summary,
        'metrics': metrics,
        'findings': findings,
        'predicted_netlist': netlist,
        'limitations': LIMITATIONS,
    }
    if topology is not None:
        result['topology'] = topology
    return result, model, texts


def render(model, texts, findings, path, scale=4.0):
    """草图预览：只用于原生建模前的快速查看，不能当作原生导出或交付图。

    .svg 只用标准库；.png 用 resvg-py 或 Pillow（与便携渲染相同的画布）。
    """
    from canvas import open_canvas

    border = model['border']
    x0, y0 = border[0] - 20, border[1] - 20
    footer = 6
    width, height = border[2] + 20 - x0, border[3] + 20 - y0 + footer

    def q(x, y):
        return x - x0, y - y0 + footer

    canvas = open_canvas(path, width, height, scale, '#ffffff')
    dark_red, navy = '#800000', '#000080'
    canvas.rect(*q(border[0], border[1]), *q(border[2], border[3]), dark_red, 0.25)
    for part in model['parts'].values():
        for box in part['rects']:
            canvas.rect(*q(box[0], box[1]), *q(box[2], box[3]), dark_red, 0.25, fill='#ffffb0')
        for a, b in part['lines']:
            canvas.lines([q(*a), q(*b)], dark_red, 0.25)
    for pin in model['pins']:
        canvas.lines([q(*pin['base']), q(*pin['hot'])], '#000000', 0.25)
    for a, b in model['wires']:
        canvas.lines([q(*a), q(*b)], navy, 0.33)
    dots = set(model['junctions'])
    # AD 在热端或端口锚点落在导线中段时自动显示连接点。
    for point in [pin['hot'] for pin in model['pins']] + [port['at'] for port in model['ports']]:
        if any(interior(point, seg) for seg in model['wires']):
            dots.add(point)
    for point in dots:
        canvas.ellipse(*q(*point), 1.5, 1.5, navy, 0.1, fill=navy)
    for port in model['ports']:
        x, y = port['at']
        if port['style'] in GROUND_STYLES:
            canvas.lines([q(x, y), q(x, y - 8)], dark_red, 0.25)
            for k, half in enumerate((10, 6, 2)):
                canvas.lines([q(x - half, y - 8 - 4 * k), q(x + half, y - 8 - 4 * k)], dark_red, 0.25)
        else:
            canvas.lines([q(x, y), q(x, y + 8)], dark_red, 0.25)
            canvas.lines([q(x - 8, y + 8), q(x + 8, y + 8)], dark_red, 0.25)
    for item in texts:
        ink = item['ink']
        size = EM_PER_PT * item.get('pt', model['system_pt'])
        fill = dark_red if item['kind'] in ('label', 'power') else navy
        if item.get('orientation', 0) % 2:
            # 逆时针 90°：基线在字形框右侧，文字自下而上。
            canvas.text(*q(ink[2], ink[1]), item['text'], size, fill, rotation=1)
        else:
            canvas.text(*q(ink[0], ink[1]), item['text'], size, fill)
    for n, finding in enumerate(f for f in findings if f['severity'] != 'info'):
        if 'at' not in finding:
            continue
        x, y = finding['at'][:2]
        mark = '#dc0000' if finding['severity'] == 'error' else '#e67800'
        canvas.ellipse(*q(x, y), 3, 3, mark, 0.5)
        canvas.text(*q(x + 3.5, y + 1.5), str(n + 1), 3, mark, family='sans')
    canvas.text(1.5, 1.5, 'Draft preview from check_layout.py - not a native Altium export', 3.5, '#787878', 'sans')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, '#ffffff')
    return {
        'preview': str(path),
        'source': 'portable_render',
        'renderer': canvas.renderer,
        'pixel_size': list(getattr(canvas, 'final', canvas.size)),
    }


def check_plan(plan, preview=None, scale=4.0):
    from native_ad import build

    sheet = build(plan)
    result, model, texts = check_records(sheet.records, plan.get('pin_map'), grid=plan.get('grid', 10))
    if preview:
        try:
            result['preview'] = render(model, texts, result['findings'], preview, scale)
        except (ImportError, RuntimeError):
            result['preview'] = {'status': 'PNG 草图需要 resvg-py 或 Pillow；改用 .svg 路径只需标准库'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', type=Path, help='native_ad.py create 使用的 JSON 计划')
    parser.add_argument('--output', type=Path, help='写出完整 JSON 报告')
    parser.add_argument('--preview', type=Path, help='写出草图预览：.svg 只用标准库，.png 需要 resvg-py 或 Pillow')
    parser.add_argument('--scale', type=float, default=4.0, help='预览像素/10mil，默认 4')
    parser.add_argument('--strict', action='store_true', help='warning 也视为未通过')
    args = parser.parse_args()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        if args.output and args.output.resolve() == args.plan.resolve():
            raise ValueError('输出路径不能覆盖计划')
        if not 1 <= args.scale <= 20:
            raise ValueError('scale 须在 1–20 之间')
        result = check_plan(json.loads(args.plan.read_text(encoding='utf-8-sig')), args.preview, args.scale)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + '\n', encoding='utf-8')
        brief = {k: result[k] for k in ('summary', 'metrics')}
        brief['findings'] = [f for f in result['findings'] if f['severity'] != 'info'] or result['findings']
        if 'preview' in result:
            brief['preview'] = result['preview']
        print(json.dumps(brief, ensure_ascii=False, indent=2))
        failed = result['summary']['errors'] or (args.strict and result['summary']['warnings'])
        return 1 if failed else 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
