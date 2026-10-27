"""PSIM 便携渲染：不依赖 PSIM，把建模计划画成与原生导出相近的 SVG/PNG，供排查和预览。

已标定元件按原生导出的形状绘制，其他元件画成带类型名的方框。渲染结果不是原生导出；
交付和对外说明须使用 PSIM 原生出图或真实窗口截图。
"""

from collections import Counter
import json
import math
from pathlib import Path

from canvas import open_canvas
from psim_plan import CLOCK_RADIUS, display_text, kind, origin, ports, rotate, symbol_box, wire_points

ELEMENT, WIRE, TEXT, DOT = '#0000ff', '#ff0000', '#000000', '#000000'
STROKE = 0.5


def _bounds(plan):
    boxes = []
    for element in plan['elements']:
        if kind(element) == 'WIRE':
            (x1, y1), (x2, y2) = wire_points(element)
            boxes.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            continue
        box = symbol_box(element)
        start = origin(element)
        if box is None and start is not None:
            box = (start[0] - 10, start[1] - 10, start[0] + 10, start[1] + 10)
        if box:
            boxes.append(box)
        boxes += [tuple(label['AREA']) for label in element.get('textlinks', [])]
    if not boxes:
        raise ValueError('计划里没有可绘制的元件')
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _symbol(canvas, element, shift):
    t, attrs = kind(element), element.get('attributes', {})
    start = origin(element)
    direction = attrs.get('DIRECTION', 0)

    def at(u, v):
        du, dv = rotate((u, v), direction)
        return start[0] + du - shift[0], start[1] + dv - shift[1]

    def line(*points):
        canvas.lines([at(*p) for p in points], ELEMENT, STROKE)

    def circle(u, v, r, fill=None):
        x, y = at(u, v)
        canvas.ellipse(x, y, r, r, ELEMENT, STROKE, fill)

    if t == 'R':
        line((0, 0), (9, 0))
        step = 32 / 6
        line(*[(9, 0)] + [(9 + step * (k + 0.5), -6 if k % 2 == 0 else 6) for k in range(6)] + [(41, 0)])
        line((41, 0), (50, 0))
    elif t == 'L':
        line((0, 0), (10, 0))
        for k in range(4):
            cx = 13.75 + 7.5 * k
            line(*[(cx - 3.75 * math.cos(math.pi * i / 12), -3.75 * math.sin(math.pi * i / 12)) for i in range(13)])
        line((40, 0), (50, 0))
    elif t == 'C':
        line((0, 0), (23.5, 0))
        line((23.5, -7), (23.5, 7))
        line((26.5, -7), (26.5, 7))
        line((26.5, 0), (50, 0))
    elif t in ('VDC', 'VSIN'):
        line((0, 0), (0, 15))
        line((0, 35), (0, 50))
        circle(0, 25, 10)
        if t == 'VDC':
            line((-3, 20.5), (3, 20.5))
            line((0, 17.5), (0, 23.5))
            line((-3, 29.5), (3, 29.5))
        else:
            line(*[(-6 + 12 * i / 16, 25 - 4 * math.sin(2 * math.pi * i / 16)) for i in range(17)])
    elif t == 'VP':
        line((0, 0), (0, -10))
        circle(0, -20, 10)
        x, y = at(0, -20)
        canvas.text(x, y + 3.5, 'V', 9, ELEMENT, 'serif', anchor='middle')
    elif t == 'GROUND':
        line((0, 0), (0, 10))
        for offset, half in ((10, 6.5), (13.5, 4), (16.5, 1.8)):
            line((-half, offset), (half, offset))
    elif t == 'SIMCONTROL':
        x, y = start[0] - shift[0], start[1] - shift[1]
        r = CLOCK_RADIUS
        canvas.ellipse(x, y, r, r, ELEMENT, STROKE)
        canvas.lines([(x, y - r), (x, y), (x + r, y)], ELEMENT, STROKE)
        canvas.lines([(x - r, y), (x - r + 4, y)], ELEMENT, STROKE)
        canvas.lines([(x, y + r), (x, y + r - 4)], ELEMENT, STROKE)
        return
    else:
        canvas.rect(*at(-10, -10), *at(10, 10), ELEMENT, STROKE)
        x, y = at(0, 0)
        canvas.text(x, y + 2, t, 5, ELEMENT, 'sans', anchor='middle')
    if str(attrs.get('CurrentFlag', 0)) == '1':
        circle(5, -6, 0.8)


def render_plan(plan, target, scale=4.0, margin=20, **canvas_options):
    """渲染为 .svg 或 .png（PNG 可选 resvg-py 或 Pillow）；返回输出信息。"""
    x1, y1, x2, y2 = _bounds(plan)
    shift = (x1 - margin, y1 - margin)
    width, height = x2 - x1 + 2 * margin, y2 - y1 + 2 * margin
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = open_canvas(target, width, height, scale, '#ffffff', y_up=False, **canvas_options)
    connections = Counter()
    wires = []
    for element in plan['elements']:
        if kind(element) == 'WIRE':
            a, b = wire_points(element)
            wires.append((a, b))
            connections.update([a, b])
            canvas.lines([(a[0] - shift[0], a[1] - shift[1]), (b[0] - shift[0], b[1] - shift[1])], WIRE, STROKE)
        elif kind(element) not in ('TEXT', 'TEXTLINK') and origin(element) is not None:
            _symbol(canvas, element, shift)
            connections.update(ports(element))

    def inside(p, segment):
        (ax, ay), (bx, by) = segment
        return (ax == bx == p[0] and min(ay, by) < p[1] < max(ay, by)) or (
            ay == by == p[1] and min(ax, bx) < p[0] < max(ax, bx)
        )

    # PSIM 在三个及以上连接汇合处画实心连接点。
    for p, count in connections.items():
        if count >= 3 or (count >= 1 and any(inside(p, s) for s in wires)):
            canvas.ellipse(p[0] - shift[0], p[1] - shift[1], 1.5, 1.5, DOT, 0.3, DOT)
    for element in plan['elements']:
        for label in element.get('textlinks', []):
            ax, ay = label['AREA'][:2]
            size = abs(float(label.get('FontSize', -15)))
            canvas.text(
                ax + 1.5 - shift[0],
                ay + 0.79 * size - shift[1],
                display_text(element, label['FieldName']),
                0.8 * size,
                TEXT,
                'sans',
            )
    canvas.save(target, '#ffffff')
    return {
        'render': str(target.resolve()),
        'source': 'portable_render',
        'renderer': canvas.renderer,
        'native_verified': False,
        'font_profile': canvas.font_profile,
        'pixel_size': list(getattr(canvas, 'final', canvas.size)),
        'note': '便携渲染，不是 PSIM 原生导出',
    }


def render_file(source, target, scale=4.0, **canvas_options):
    source = Path(source)
    if source.suffix.lower() != '.json':
        raise ValueError('便携渲染读取建模计划 JSON；psimsch 是 PSIM 私有二进制格式，需在 Windows 上原生导出')
    return render_plan(json.loads(source.read_text(encoding='utf-8-sig')), target, scale, **canvas_options)
