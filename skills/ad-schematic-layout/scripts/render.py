"""便携渲染：不依赖 AD，把 SchDoc 记录画成与原生导出相近的 SVG/PNG，供排查和预览。

渲染结果不是原生导出；交付和对外说明须使用 AD 原生出图或真实窗口截图。
"""

import math
from pathlib import Path

from canvas import color, open_canvas
from schdoc import pin_end, point

# 原生导出标定：字号每 pt 约 0.85 个 10 mil 单位的 em，基线比锚点高约 0.24 pt。
EM_PER_PT = 0.85
BASELINE_PER_PT = 0.24
LINE_WIDTHS = {0: 0.4, 1: 1.0, 2: 2.0, 3: 4.0}


def _font(sheet, font_id):
    font_id = int(float(font_id or sheet.get('SYSTEMFONT', 1)))
    name = sheet.get(f'FONTNAME{font_id}', 'Times New Roman')
    family = 'sans' if any(k in name.lower() for k in ('arial', 'sans', 'helvetica', 'calibri')) else 'serif'
    return (
        float(sheet.get(f'SIZE{font_id}', 10)),
        family,
        sheet.get(f'BOLD{font_id}') == 'T',
        sheet.get(f'ITALIC{font_id}') == 'T',
    )


def _text(canvas, sheet, x, y, value, font_id, fill, orientation=0, justification=0):
    size, family, bold, italic = _font(sheet, font_id)
    em = EM_PER_PT * size
    horizontal = ('start', 'middle', 'end')[justification % 3]
    vertical = min(justification // 3, 2)
    # 锚点在字格底边；居中、顶对齐时把基线下移。
    rise = (BASELINE_PER_PT * size, BASELINE_PER_PT * size - 0.5 * size, BASELINE_PER_PT * size - size)[vertical]
    dx, dy = {0: (0, rise), 1: (-rise, 0), 2: (0, -rise), 3: (rise, 0)}[orientation % 4]
    canvas.text(x + dx, y + dy, value, em, fill, family, orientation % 4, horizontal, bold, italic)


def _zones(canvas, sheet, width, height):
    margin = float(sheet.get('CUSTOMMARGINWIDTH', 20))
    xs, ys = int(sheet.get('CUSTOMXZONES', 6)), int(sheet.get('CUSTOMYZONES', 4))
    ink = color(sheet.get('BORDERCOLOR', 0))
    canvas.rect(margin, margin, width - margin, height - margin, ink, 0.5)
    # AD 按整张图纸等分参考分区，分区线只画在边框带内。
    step_x, step_y = width / xs, height / ys
    size = EM_PER_PT * 8
    for i in range(xs):
        x = step_x * i
        if i:
            for y0, y1 in ((0, margin), (height - margin, height)):
                canvas.lines([(x, y0), (x, y1)], ink, 0.5)
        for y in (margin / 2 - 0.35 * size, height - margin / 2 - 0.35 * size):
            canvas.text(x + step_x / 2, y, str(i + 1), size, ink, anchor='middle')
    for j in range(ys):
        y = height - step_y * j
        if j:
            for x0, x1 in ((0, margin), (width - margin, width)):
                canvas.lines([(x0, y), (x1, y)], ink, 0.5)
        letter = chr(ord('A') + j % 26)
        for x in (margin / 2, width - margin / 2):
            canvas.text(x, y - step_y / 2 - 0.35 * size, letter, size, ink, anchor='middle')


def _arc_points(cx, cy, rx, ry, start, end, steps=48):
    if end <= start:
        end += 360
    count = max(4, int(steps * (end - start) / 360))
    return [
        (
            cx + rx * math.cos(math.radians(start + (end - start) * k / count)),
            cy + ry * math.sin(math.radians(start + (end - start) * k / count)),
        )
        for k in range(count + 1)
    ]


def _points(record):
    count = int(record.get('LOCATIONCOUNT', 0))
    return [
        (
            float(record.get(f'X{i}', 0)) + float(record.get(f'X{i}_FRAC', 0)) / 1e5,
            float(record.get(f'Y{i}', 0)) + float(record.get(f'Y{i}_FRAC', 0)) / 1e5,
        )
        for i in range(1, count + 1)
    ]


def _bezier(points):
    result = []
    for i in range(0, len(points) - 3, 3):
        p0, p1, p2, p3 = points[i : i + 4]
        for k in range(17):
            t = k / 16
            result.append(
                tuple(
                    (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t**2 * c + t**3 * d
                    for a, b, c, d in zip(p0, p1, p2, p3)
                )
            )
    return result


def _power(canvas, sheet, record, ink):
    x, y = point(record)
    style = int(record.get('STYLE', 2))
    turn = int(record.get('ORIENTATION', 0)) % 4

    def at(u, v):
        # u 沿符号朝向，v 为横向；朝向 1 为向上。
        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[turn]
        return x + dx * u - dy * v, y + dy * u + dx * v

    if style in (4, 5, 6):
        canvas.lines([at(0, 0), at(10, 0)], ink, 1)
        widths = {4: (10, 7, 4, 1), 5: (10,), 6: (10, 7, 4, 1)}[style]
        for k, half in enumerate(widths):
            canvas.lines([at(10 + 3 * k, -half), at(10 + 3 * k, half)], ink, 1)
        reach = 10 + 3 * (len(widths) - 1)
    elif style == 0:
        canvas.lines([at(0, 0), at(6, 0)], ink, 1)
        cx, cy = at(8, 0)
        canvas.ellipse(cx, cy, 2, 2, ink, 1)
        reach = 10
    elif style == 1:
        canvas.lines([at(0, 0), at(6, 0)], ink, 1)
        canvas.lines([at(6, -3), at(10, 0), at(6, 3)], ink, 1, True)
        reach = 10
    else:
        canvas.lines([at(0, 0), at(10, 0)], ink, 1)
        canvas.lines([at(10, -5), at(10, 5)], ink, 1)
        reach = 10
    if record.get('SHOWNETNAME', 'T') == 'T' and record.get('TEXT'):
        size, family, _, _ = _font(sheet, record.get('FONTID'))
        em = EM_PER_PT * size
        tx, ty = at(reach + 2, 0)
        if turn == 1:
            canvas.text(tx, ty + 1, record['TEXT'], em, ink, family, anchor='middle')
        elif turn == 3:
            # 名称紧贴符号外侧：大写字母顶部比最后一道横线低约一个单位。
            canvas.text(tx, ty - 0.7 * em, record['TEXT'], em, ink, family, anchor='middle')
        else:
            canvas.text(tx, ty - 0.3 * size, record['TEXT'], em, ink, family, anchor='start' if turn == 0 else 'end')


def _pin(canvas, sheet, record):
    flags = int(record.get('PINCONGLOMERATE', 0))
    if flags & 4:
        return
    base, hot = point(record), pin_end(record)
    ink = color(record.get('COLOR', 0))
    canvas.lines([base, hot], ink, 1)
    direction = flags & 3
    size, family, _, _ = _font(sheet, sheet.get('SYSTEMFONT', 1))
    em = EM_PER_PT * size
    if int(record.get('SYMBOL_OUTEREDGE', 0)) == 1:
        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
        canvas.ellipse(base[0] + dx * 1.5, base[1] + dy * 1.5, 1.5, 1.5, ink, 0.8)
    name = record.get('NAME', '')
    if flags & 8 and name.strip():
        clean = name.replace('\\', '')
        gap = 7
        if direction == 0:
            canvas.text(base[0] - gap, base[1] - 0.3 * size, clean, em, ink, family, anchor='end')
        elif direction == 2:
            canvas.text(base[0] + gap, base[1] - 0.3 * size, clean, em, ink, family)
        elif direction == 1:
            canvas.text(base[0] + 0.3 * size, base[1] - gap, clean, em, ink, family, rotation=1, anchor='end')
        else:
            canvas.text(base[0] + 0.3 * size, base[1] + gap, clean, em, ink, family, rotation=1)
    number = record.get('DESIGNATOR', '')
    if flags & 16 and number.strip():
        # 引脚号从器件边沿向外偏 9 个单位对齐，基线在引脚线上方。
        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
        nx, ny = base[0] + dx * 9, base[1] + dy * 9
        anchor = 'end' if direction in (2, 3) else 'start'
        if direction in (0, 2):
            canvas.text(nx, ny + 1 + BASELINE_PER_PT * size, number, em, ink, family, anchor=anchor)
        else:
            canvas.text(nx - 1 - BASELINE_PER_PT * size, ny, number, em, ink, family, rotation=1, anchor=anchor)


def _auto_junctions(records):
    """AD 在热端、电源端口或导线端点落在另一根导线中段时自动显示连接点。"""
    wires = []
    for record in records:
        if record.get('RECORD') == '27':
            points = _points(record)
            wires += [(a, b) for a, b in zip(points, points[1:]) if a != b]
    stored = {point(r) for r in records if r.get('RECORD') == '29'}
    anchors = [pin_end(r) for r in records if r.get('RECORD') == '2']
    anchors += [point(r) for r in records if r.get('RECORD') == '17']
    anchors += [p for segment in wires for p in segment]

    def inside(p, segment):
        (x1, y1), (x2, y2) = segment
        if x1 == x2 == p[0]:
            return min(y1, y2) < p[1] < max(y1, y2)
        if y1 == y2 == p[1]:
            return min(x1, x2) < p[0] < max(x1, x2)
        return False

    return {p for p in anchors if p not in stored and any(inside(p, s) for s in wires)}


def render_records(records, target, scale=4.0, zones=True):
    """渲染为 .svg 或 .png（PNG 需要 Pillow）；返回输出信息。"""
    from plan_tools import sheet_size

    sheet = records[1]
    width, height = sheet_size(sheet)
    background = color(sheet.get('AREACOLOR', 16777215))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = open_canvas(target, width, height, scale, background)
    if zones:
        _zones(canvas, sheet, width, height)
    parts = {str(i - 1): r for i, r in enumerate(records) if r.get('RECORD') == '1'}
    # 图纸参数（未归属器件的参数记录）只供 =Title 这类引用，不直接绘制。
    document = {
        r.get('NAME', '').upper(): r.get('TEXT', '')
        for r in records
        if r.get('RECORD') == '41' and 'OWNERINDEX' not in r
    }

    def visible(record):
        owner = parts.get(record.get('OWNERINDEX'))
        if record.get('ISHIDDEN') == 'T':
            return False
        if owner is None:
            return True
        part_id = record.get('OWNERPARTID', '-1')
        if part_id not in ('-1', owner.get('CURRENTPARTID', '1')):
            return False
        return record.get('OWNERPARTDISPLAYMODE', '0') == owner.get('DISPLAYMODE', '0')

    labels = []
    for record in records[2:]:
        kind = record.get('RECORD')
        if not visible(record):
            continue
        ink = color(record.get('COLOR', 0))
        width_ = LINE_WIDTHS.get(int(record.get('LINEWIDTH', 0)), 1.0)
        fill = color(record['AREACOLOR']) if record.get('ISSOLID') == 'T' and 'AREACOLOR' in record else None
        if kind in ('27', '6', '26'):
            canvas.lines(_points(record), ink, width_ if kind != '26' else 3)
        elif kind == '5':
            canvas.lines(_bezier(_points(record)), ink, width_)
        elif kind == '7':
            canvas.lines(_points(record), ink, width_, True, fill)
        elif kind == '13':
            canvas.lines([point(record), point(record, 'CORNER')], ink, width_)
        elif kind in ('14', '10'):
            (x1, y1), (x2, y2) = point(record), point(record, 'CORNER')
            canvas.rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2), ink, width_, fill)
        elif kind == '8':
            cx, cy = point(record)
            radius = float(record.get('RADIUS', 0)) + float(record.get('RADIUS_FRAC', 0)) / 1e5
            secondary = float(record.get('SECONDARYRADIUS', radius))
            canvas.ellipse(cx, cy, radius, secondary, ink, width_, fill)
        elif kind in ('11', '12'):
            cx, cy = point(record)
            radius = float(record.get('RADIUS', 0)) + float(record.get('RADIUS_FRAC', 0)) / 1e5
            secondary = float(record.get('SECONDARYRADIUS', radius)) if kind == '11' else radius
            start, end = float(record.get('STARTANGLE', 0)), float(record.get('ENDANGLE', 360))
            canvas.lines(_arc_points(cx, cy, radius, secondary, start, end), ink, width_)
        elif kind == '2':
            _pin(canvas, sheet, record)
        elif kind == '29':
            cx, cy = point(record)
            canvas.ellipse(cx, cy, 1.8, 1.8, ink, 0.5, ink)
        elif kind == '17':
            _power(canvas, sheet, record, ink)
        elif kind == '22':
            x, y = point(record)
            canvas.lines([(x - 3, y - 3), (x + 3, y + 3)], color(record.get('COLOR', 255)), 1)
            canvas.lines([(x - 3, y + 3), (x + 3, y - 3)], color(record.get('COLOR', 255)), 1)
        elif kind in ('4', '25', '34') or (kind == '41' and 'OWNERINDEX' in record):
            labels.append(record)
    for x, y in _auto_junctions(records):
        canvas.ellipse(x, y, 1.8, 1.8, color(8388608), 0.5, color(8388608))
    for record in labels:
        value = record.get('TEXT', '')
        if value.startswith('='):
            value = document.get(value[1:].upper())
            if value is None:
                continue
        x, y = point(record)
        _text(
            canvas,
            sheet,
            x,
            y,
            value,
            record.get('FONTID'),
            color(record.get('COLOR', 0)),
            int(record.get('ORIENTATION', 0)),
            int(record.get('JUSTIFICATION', 0)),
        )
    canvas.save(target, background)
    return {
        'render': str(target.resolve()),
        'source': 'portable_render',
        'pixel_size': list(getattr(canvas, 'final', canvas.size)),
        'note': '便携渲染，不是 AD 原生导出',
    }


def render_file(source, target, scale=4.0):
    """source 可为 SchDoc 或计划 JSON。"""
    import json

    from native_ad import build
    from schdoc import read

    source = Path(source)
    if source.suffix.lower() == '.json':
        records = build(json.loads(source.read_text(encoding='utf-8-sig'))).records
    else:
        records = read(source)
    return render_records(records, target, scale)
