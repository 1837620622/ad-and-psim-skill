"""审查原生 EMF 的文字：字框重叠、越出图框，以及文字被导线或符号线条穿过（压线）。

AD 与 PSIM 原生导出都可使用。坐标统一换算到 EMF 设备坐标；不检查字形美观、参数真实性或电气连接。
"""

import argparse
import json
import math
import struct
from pathlib import Path
import sys

# 带 Bounds 的折线类记录：类型 -> (点坐标为 16 位, 是否多段)
POLY = {
    2: (False, False),
    3: (False, False),
    4: (False, False),
    5: (False, False),
    6: (False, False),
    7: (False, True),
    8: (False, True),
    85: (True, False),
    86: (True, False),
    87: (True, False),
    88: (True, False),
    89: (True, False),
    90: (True, True),
    91: (True, True),
}
CLOSED = {3, 8, 86, 91}
CONTINUES = {5, 6, 88, 89}
ARCS = {41, 45, 46, 47, 55}
# 固定映射模式：逻辑单位对应的毫米数，y 轴向上。
METRIC = {2: 0.1, 3: 0.01, 4: 0.254, 5: 0.0254, 6: 25.4 / 1440}


def multiply(a, b):
    """XFORM 乘法，按 GDI 的行向量约定：[x y 1]·A·B。"""
    a11, a12, a21, a22, ax, ay = a
    b11, b12, b21, b22, bx, by = b
    return (
        a11 * b11 + a12 * b21,
        a11 * b12 + a12 * b22,
        a21 * b11 + a22 * b21,
        a21 * b12 + a22 * b22,
        ax * b11 + ay * b21 + bx,
        ax * b12 + ay * b22 + by,
    )


class Mapping:
    """跟踪映射模式、窗口/视口和世界变换，把逻辑坐标换算为设备坐标。"""

    def __init__(self, device, millimeters):
        self.pixels_per_mm = (
            device[0] / millimeters[0] if millimeters[0] else 3.78,
            device[1] / millimeters[1] if millimeters[1] else 3.78,
        )
        self.state = {
            'mode': 1,
            'worg': (0, 0),
            'wext': (1, 1),
            'vorg': (0, 0),
            'vext': (1, 1),
            'world': (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        }
        self.stack = []

    def __call__(self, x, y):
        s = self.state
        m11, m12, m21, m22, dx, dy = s['world']
        x, y = x * m11 + y * m21 + dx, x * m12 + y * m22 + dy
        mode = s['mode']
        if mode in METRIC:
            sx = METRIC[mode] * self.pixels_per_mm[0]
            sy = -METRIC[mode] * self.pixels_per_mm[1]
        elif mode in (7, 8):
            sx = s['vext'][0] / s['wext'][0] if s['wext'][0] else 1.0
            sy = s['vext'][1] / s['wext'][1] if s['wext'][1] else 1.0
        else:
            sx = sy = 1.0
        return ((x - s['worg'][0]) * sx + s['vorg'][0], (y - s['worg'][1]) * sy + s['vorg'][1])

    def record(self, kind, raw, offset):
        s = self.state
        if kind == 17:
            s['mode'] = struct.unpack_from('<I', raw, offset + 8)[0]
        elif kind in (9, 10, 11, 12):
            key = {9: 'wext', 10: 'worg', 11: 'vext', 12: 'vorg'}[kind]
            s[key] = struct.unpack_from('<2i', raw, offset + 8)
        elif kind in (31, 32):
            xn, xd, yn, yd = struct.unpack_from('<4i', raw, offset + 8)
            key = 'vext' if kind == 31 else 'wext'
            if xd and yd:
                s[key] = (s[key][0] * xn / xd, s[key][1] * yn / yd)
        elif kind == 33:
            self.stack.append(dict(s))
        elif kind == 34:
            level = struct.unpack_from('<i', raw, offset + 8)[0]
            for _ in range(-level if level < 0 else 1):
                if self.stack:
                    self.state = self.stack.pop()
        elif kind == 35:
            s['world'] = struct.unpack_from('<6f', raw, offset + 8)
        elif kind == 36:
            xform = struct.unpack_from('<6f', raw, offset + 8)
            mode = struct.unpack_from('<I', raw, offset + 32)[0]
            if mode == 1:
                s['world'] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            elif mode == 2:
                s['world'] = multiply(xform, s['world'])
            elif mode == 3:
                s['world'] = multiply(s['world'], xform)
            elif mode == 4:
                s['world'] = xform


def ellipse_points(box, mapping, steps=32):
    x1, y1, x2, y2 = box
    cx, cy, rx, ry = (x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1) / 2, abs(y2 - y1) / 2
    points = [
        mapping(cx + rx * math.cos(2 * math.pi * k / steps), cy + ry * math.sin(2 * math.pi * k / steps))
        for k in range(steps)
    ]
    return points + points[:1]


def parse_emf(raw):
    """返回 (header bounds, 文字, 未支持文字记录计数, 无效字框数, 线段, 线条覆盖信息)。"""
    if len(raw) < 88 or struct.unpack_from('<I', raw)[0] != 1 or raw[40:44] != b' EMF':
        raise ValueError('不是有效的 EMF 文件头')
    bounds = struct.unpack_from('<4i', raw, 8)
    device = struct.unpack_from('<2i', raw, 72)
    millimeters = struct.unpack_from('<2i', raw, 80)
    mapping = Mapping(device, millimeters)
    offset, texts, unsupported, invalid = 0, [], {}, 0
    segments, current = [], None
    coverage = {'checked_records': 0, 'bounds_mismatch': 0, 'unchecked_arc_records': 0}
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError('EMF 记录头截断')
        kind, size = struct.unpack_from('<II', raw, offset)
        if size < 8 or size % 4 or offset + size > len(raw):
            raise ValueError(f'EMF 记录大小无效，偏移 {offset}')
        mapping.record(kind, raw, offset)
        if kind == 84:
            if size < 76:
                raise ValueError('Unicode 文字记录截断')
            count, at = struct.unpack_from('<II', raw, offset + 44)
            if count and (at < 76 or at + count * 2 > size):
                raise ValueError('Unicode 文字超出所属记录')
            text = raw[offset + at : offset + at + count * 2].decode('utf-16le')
            box = struct.unpack_from('<4i', raw, offset + 8)
            if text.strip():
                if box[2] <= box[0] or box[3] <= box[1]:
                    invalid += 1
                else:
                    texts.append({'text': text, 'box': list(box)})
        elif kind in (83, 96, 97, 108):
            unsupported[str(kind)] = unsupported.get(str(kind), 0) + 1
        elif kind in POLY:
            short, multi = POLY[kind]
            record_bounds = struct.unpack_from('<4i', raw, offset + 8)
            fmt, width = ('<2h', 4) if short else ('<2i', 8)
            if multi:
                polys, total = struct.unpack_from('<II', raw, offset + 24)
                counts = struct.unpack_from(f'<{polys}I', raw, offset + 32)
                start = offset + 32 + 4 * polys
            else:
                total = struct.unpack_from('<I', raw, offset + 24)[0]
                counts, start = (total,), offset + 28
            if start + total * width > offset + size:
                raise ValueError(f'EMF 折线点超出记录，偏移 {offset}')
            points = [mapping(*struct.unpack_from(fmt, raw, start + i * width)) for i in range(total)]
            if record_bounds[2] >= record_bounds[0] and record_bounds[3] >= record_bounds[1] and points:
                coverage['checked_records'] += 1
                xs, ys = [p[0] for p in points], [p[1] for p in points]
                slack = 3 + 0.02 * max(record_bounds[2] - record_bounds[0], record_bounds[3] - record_bounds[1])
                if (
                    min(xs) < record_bounds[0] - slack
                    or max(xs) > record_bounds[2] + slack
                    or min(ys) < record_bounds[1] - slack
                    or max(ys) > record_bounds[3] + slack
                ):
                    coverage['bounds_mismatch'] += 1
            index = 0
            for n in counts:
                group = points[index : index + n]
                index += n
                if kind in CONTINUES and current is not None:
                    group = [current] + group
                if kind in CLOSED and group:
                    group = group + group[:1]
                segments.extend((a, b, kind) for a, b in zip(group, group[1:]) if a != b)
                if group:
                    current = group[-1]
        elif kind == 27:
            current = mapping(*struct.unpack_from('<2i', raw, offset + 8))
        elif kind == 54:
            point = mapping(*struct.unpack_from('<2i', raw, offset + 8))
            if current is not None and current != point:
                segments.append((current, point, kind))
            current = point
        elif kind in (43, 44):
            x1, y1, x2, y2 = struct.unpack_from('<4i', raw, offset + 8)
            corners = [mapping(x1, y1), mapping(x2, y1), mapping(x2, y2), mapping(x1, y2)]
            segments.extend((a, b, kind) for a, b in zip(corners, corners[1:] + corners[:1]))
        elif kind == 42:
            box = struct.unpack_from('<4i', raw, offset + 8)
            outline = ellipse_points(box, mapping)
            segments.extend((a, b, kind) for a, b in zip(outline, outline[1:]))
        elif kind in ARCS:
            coverage['unchecked_arc_records'] += 1
        offset += size
    return bounds, texts, unsupported, invalid, segments, coverage


def text_core(box, text=''):
    """去掉字格上方行距与下方降部，只保留大写字母与数字所在的带状区域。"""
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    # 单个字符的字框本来就偏窄高，不能据此判定为竖排。
    if len(text.strip()) > 1 and height > 1.5 * width:
        return (x1 + 0.25 * width, y1 + 1, x2 - 0.22 * width, y2 - 1)
    return (x1 + 1, y1 + 0.22 * height, x2 - 1, y2 - 0.25 * height)


def crosses(a, b, box):
    """线段是否进入开区间矩形（Liang-Barsky 裁剪）。"""
    if box[2] <= box[0] or box[3] <= box[1]:
        return False
    (x1, y1), (x2, y2) = a, b
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


def review(raw, border=None, overlap_ratio=0.2):
    bounds, texts, unsupported, invalid, segments, coverage = parse_emf(raw)
    border = border or bounds
    if border[2] <= border[0] or border[3] <= border[1]:
        raise ValueError('边界必须为 xmin,ymin,xmax,ymax')
    overlaps = []
    for i, a in enumerate(texts):
        x1, y1, x2, y2 = a['box']
        area = (x2 - x1) * (y2 - y1)
        for j in range(i + 1, len(texts)):
            u1, v1, u2, v2 = texts[j]['box']
            intersection = max(0, min(x2, u2) - max(x1, u1)) * max(0, min(y2, v2) - max(y1, v1))
            ratio = intersection / min(area, (u2 - u1) * (v2 - v1))
            if ratio > overlap_ratio:
                overlaps.append(
                    {'first': i, 'second': j, 'fraction_of_smaller_box': ratio, 'texts': [a['text'], texts[j]['text']]}
                )
    outside = [
        i
        for i, a in enumerate(texts)
        if a['box'][0] < border[0] or a['box'][1] < border[1] or a['box'][2] > border[2] or a['box'][3] > border[3]
    ]
    reliable = coverage['checked_records'] == 0 or coverage['bounds_mismatch'] <= 0.2 * coverage['checked_records']
    conflicts = []
    if reliable:
        for i, item in enumerate(texts):
            core = text_core(item['box'], item['text'])
            hits = [(a, b, kind) for a, b, kind in segments if crosses(a, b, core)]
            if hits:
                a, b, kind = hits[0]
                conflicts.append(
                    {
                        'index': i,
                        'text': item['text'],
                        'box': item['box'],
                        'line_count': len(hits),
                        'first_line': [[round(v, 1) for v in a], [round(v, 1) for v in b]],
                        'record_type': kind,
                    }
                )
    line_check = dict(coverage, segments=len(segments), transform_reliable=reliable)
    complete = not (unsupported or invalid) and reliable
    return {
        'text_count': len(texts),
        'border': list(border),
        'overlaps': overlaps,
        'outside_indices': outside,
        'text_line_conflicts': conflicts,
        'line_check': line_check,
        'texts': texts,
        'unsupported_text_record_counts': unsupported,
        'invalid_text_bounds': invalid,
        'coverage_complete_for_text_records': complete,
        'limitations': '文字取原生字框，线条按映射模式换算；圆弧记录未参与压线判断，'
        '不检查字形美观、参数真实性或电气连接，仍须查看全图与局部。',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('emf', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--border', help='EMF 设备坐标 xmin,ymin,xmax,ymax')
    parser.add_argument('--overlap-ratio', type=float, default=0.2)
    args = parser.parse_args()
    try:
        if not 0 < args.overlap_ratio <= 1:
            raise ValueError('overlap-ratio 须在 (0,1] 内')
        border = [float(v) for v in args.border.split(',')] if args.border else None
        if border is not None and len(border) != 4:
            raise ValueError('border 须有四个数')
        if args.output and args.output.resolve() == args.emf.resolve():
            raise ValueError('输出路径不能覆盖输入')
        result = review(args.emf.read_bytes(), border, args.overlap_ratio)
        if args.output:
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'texts'}, ensure_ascii=False, indent=2))
        return int(
            bool(
                result['overlaps']
                or result['outside_indices']
                or result['text_line_conflicts']
                or not result['coverage_complete_for_text_records']
            )
        )
    except (ValueError, OSError, UnicodeError, struct.error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
