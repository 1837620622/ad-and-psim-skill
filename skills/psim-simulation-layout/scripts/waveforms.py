"""把波形 CSV 画成曲线图并转成 Excel 表：PNG 需要 Pillow，没有时写 SVG；XLSX 只用标准库写出。

每个信号一栏，共用时间轴。每个像素列画该列全部样本的最小到最大值（包络），长波形里的尖峰和振荡不会被抽稀掉。
曲线是按 CSV 数据绘制的结果图，不是 SIMVIEW 截图。
"""

import argparse
import csv
from html import escape
import itertools
import json
import math
from pathlib import Path
import sys
import zipfile

MAX_ROWS = 1_048_576  # Excel 每张表的行数上限（含表头）
MAX_PANELS = 12
WIDTH, PANEL, GAP, LEFT, RIGHT, TOP, BOTTOM = 1600, 200, 44, 110, 36, 16, 78
SCALE = 2  # 先按 2 倍画再缩小，线和字有抗锯齿
SURFACE, INK, MUTED, GRID, AXIS, TRACE = '#ffffff', '#0b0b0b', '#52514e', '#e6e5e0', '#8a8985', '#2a78d6'
# 中文信号名用的无衬线中文字体（Windows、macOS、Linux 常见位置）；西文用 canvas 找到的 Arial 或同度量字体。
CJK_FONTS = (
    'msyh.ttc',
    'simhei.ttf',
    'simsun.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
)
SVG_FONTS = "Arial, 'Liberation Sans', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', sans-serif"
PREFIXES = ((1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1, ''), (1e-3, 'm'), (1e-6, 'µ'), (1e-9, 'n'), (1e-12, 'p'))


# ---------------------------------------------------------------- 读取 ----
def _number(text):
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _columns(path, signals):
    with open(path, newline='', encoding='utf-8-sig') as stream:
        header = [name.strip() for name in next(csv.reader(stream), [])]
    if len(set(header)) != len(header):
        raise ValueError('CSV 列名重复')
    time = next((i for i, name in enumerate(header) if name.casefold() == 'time'), None)
    if time is None:
        raise ValueError('CSV 缺少 Time 列')
    if signals:
        missing = [s for s in signals if s not in header]
        if missing:
            raise ValueError(f'CSV 里没有这些列：{"、".join(missing)}；现有列：{"、".join(header)}')
        chosen = [header.index(s) for s in signals if header.index(s) != time]
    else:
        chosen = [i for i in range(len(header)) if i != time]
    if not chosen:
        raise ValueError('除 Time 外没有可画的信号')
    return header, time, chosen


def _rows(path, time, chosen, start, end):
    """逐行给出 (时间, 各信号值)；跳过时间窗外和时间无效的行，时间须递增。"""
    previous = None
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        next(reader, None)
        for line, row in enumerate(reader, 2):
            if not row or all(not cell.strip() for cell in row):
                continue
            t = _number(row[time]) if time < len(row) else None
            if t is None:
                raise ValueError(f'第 {line} 行的 Time 不是有限数值')
            if previous is not None and t < previous:
                raise ValueError(f'第 {line} 行的 Time 比上一行小')
            previous = t
            if (start is not None and t < start) or (end is not None and t > end):
                continue
            yield t, [_number(row[i]) if i < len(row) else None for i in chosen]


# ---------------------------------------------------------------- 统计 ----
class Stats:
    """单个信号的最小、最大、末值与按时间加权（梯形）的平均值和有效值。"""

    def __init__(self):
        self.low = self.high = self.last = self.last_time = None
        self.area = self.square = self.span = 0.0

    def add(self, t, value):
        if value is None:
            return
        if self.last is not None and t > self.last_time:
            step = t - self.last_time
            self.area += (self.last + value) / 2 * step
            self.square += (self.last**2 + self.last * value + value**2) / 3 * step
            self.span += step
        self.low = value if self.low is None else min(self.low, value)
        self.high = value if self.high is None else max(self.high, value)
        self.last, self.last_time = value, t

    def summary(self):
        if self.low is None:
            return dict.fromkeys(('min', 'max', 'final', 'mean', 'rms'))
        mean = self.area / self.span if self.span else self.last
        rms = math.sqrt(max(self.square / self.span, 0.0)) if self.span else abs(self.last)
        return {'min': self.low, 'max': self.high, 'final': self.last, 'mean': mean, 'rms': rms}


# ---------------------------------------------------------------- XLSX ----
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
STYLES = (
    f'{XML}<styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill '
    'patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1">'
    '<border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" '
    'fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" '
    'borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
)


def _letters(index):
    name = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _cell(reference, value, style=0):
    styled = f' s="{style}"' if style else ''
    if value is None or value == '':
        return ''
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}"{styled}><v>{value!r}</v></c>'
    return f'<c r="{reference}"{styled} t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


class Workbook:
    """流式写 XLSX：每张表直接写进压缩包，内存只占一行；压缩包内时间戳固定，同样的数据得到同样的文件。"""

    def __init__(self, path):
        self.archive = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6)
        self.sheets = []

    def _open(self, name):
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
        return self.archive.open(info, 'w', force_zip64=True)

    def _write(self, name, text):
        with self._open(name) as stream:
            stream.write(text.encode('utf-8'))

    def sheet(self, title, rows, widths=(), frozen=True):
        """rows 的第一行是表头（加粗）；返回写入的数据行数，不含表头。"""
        number = len(self.sheets) + 1
        self.sheets.append(title)
        columns = ''.join(
            f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)
        )
        pane = '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' if frozen else ''
        count = -1
        with self._open(f'xl/worksheets/sheet{number}.xml') as stream:
            stream.write(
                f'{XML}<worksheet xmlns="{NS}"><sheetViews><sheetView workbookViewId="0">{pane}</sheetView>'
                f'</sheetViews>{f"<cols>{columns}</cols>" if columns else ""}<sheetData>'.encode()
            )
            for count, row in enumerate(rows):
                line = count + 1
                cells = ''.join(_cell(f'{_letters(i)}{line}', v, 1 if count == 0 else 0) for i, v in enumerate(row))
                stream.write(f'<row r="{line}">{cells}</row>'.encode())
            stream.write(b'</sheetData></worksheet>')
        return max(count, 0)

    def close(self):
        n = len(self.sheets)
        sheets = ''.join(
            f'<sheet name="{escape(t)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, t in enumerate(self.sheets)
        )
        self._write(
            'xl/workbook.xml', f'{XML}<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>{sheets}</sheets></workbook>'
        )
        links = ''.join(
            f'<Relationship Id="rId{i + 1}" Type="{REL}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(n)
        )
        self._write(
            'xl/_rels/workbook.xml.rels',
            f'{XML}<Relationships xmlns="{PKG}">{links}'
            f'<Relationship Id="rId{n + 1}" Type="{REL}/styles" Target="styles.xml"/></Relationships>',
        )
        self._write('xl/styles.xml', STYLES)
        self._write(
            '_rels/.rels',
            f'{XML}<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        sheet_types = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(n)
        )
        self._write(
            '[Content_Types].xml',
            f'{XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f'{sheet_types}<Override PartName="/xl/styles.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        )
        self.archive.close()


# ---------------------------------------------------------------- 坐标 ----
def _ticks(low, high, count=5):
    """1-2-5 刻度：返回覆盖 [low, high] 的显示范围和刻度值。"""
    if not high > low:
        pad = abs(low) * 0.1 or 1.0
        low, high = low - pad, high + pad
    raw = (high - low) / count
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
    first, last = math.floor(low / step + 1e-9) * step, math.ceil(high / step - 1e-9) * step
    ticks = [first + i * step for i in range(round((last - first) / step) + 1)]
    return first, last, [0.0 if abs(t) < step * 1e-9 else t for t in ticks], step


def _prefix(largest):
    return next(((f, p) for f, p in PREFIXES if largest >= f * 0.9999), PREFIXES[-1])


def _labels(ticks, step, suffix=True):
    """同一坐标轴用同一个 SI 词头；小数位刚好表示出刻度间距（2.5 要 1 位）。返回 (文字列表, 词头)。"""
    factor, prefix = _prefix(max(abs(t) for t in ticks) or step)
    scaled = step / factor
    digits = next(d for d in range(13) if abs(round(scaled, d) - scaled) <= scaled * 1e-6)
    texts = ['0' if t == 0 else f'{t / factor:.{digits}f}{prefix if suffix else ""}' for t in ticks]
    return texts, prefix


def _value_axis(low, high):
    if high > low:
        pad = (high - low) * 0.05
        low, high = low - pad, high + pad
    low, high, ticks, step = _ticks(low, high)
    return low, high, ticks, _labels(ticks, step)[0]


def _time_axis(t0, t1):
    """时间轴就用数据的起止时间，刻度取范围内的整数倍；起点离 0 很近时从 0 画起。"""
    if 0 < t0 <= (t1 - t0) * 0.01:
        t0 = 0.0
    _, _, ticks, step = _ticks(t0, t1, 8)
    ticks = [t for t in ticks if t0 - step * 1e-6 <= t <= t1 + step * 1e-6]
    texts, prefix = _labels(ticks, step, suffix=False)
    return t0, t1, ticks, texts, f'Time ({prefix}s)'


def _envelope(path, time, chosen, start, end, low, high, columns):
    """每个像素列记录 (首值, 最小, 最大, 末值)。"""
    bins = [[None] * columns for _ in chosen]
    span = high - low
    for t, values in _rows(path, time, chosen, start, end):
        column = min(columns - 1, max(0, int((t - low) / span * (columns - 1) + 0.5)))
        for k, value in enumerate(values):
            if value is None:
                continue
            cell = bins[k][column]
            if cell is None:
                bins[k][column] = [value, value, value, value]
            else:
                cell[1], cell[2], cell[3] = min(cell[1], value), max(cell[2], value), value
    return bins


# ---------------------------------------------------------------- 画图 ----
def _layout(panels):
    height = TOP + panels * (GAP + PANEL) + BOTTOM
    boxes = [(LEFT, TOP + i * (GAP + PANEL) + GAP, WIDTH - RIGHT, TOP + (i + 1) * (GAP + PANEL)) for i in range(panels)]
    return height, boxes


def _segments(cells, box, low, high):
    """把包络转成线段（像素坐标）：列内的竖线加相邻列之间的连线。"""
    left, top, right, bottom = box
    width = right - left

    def y(value):
        return bottom - (value - low) / (high - low) * (bottom - top)

    previous, lines = None, []
    for column, cell in enumerate(cells):
        if cell is None:
            continue
        x = left + column / (len(cells) - 1) * width
        if previous is not None:
            lines.append(((previous[0], y(previous[1])), (x, y(cell[0]))))
        if cell[2] > cell[1]:
            lines.append(((x, y(cell[1])), (x, y(cell[2]))))
        elif previous is None:
            lines.append(((x, y(cell[0])), (x, y(cell[0]))))
        previous = (x, cell[3])
    return lines


def _fonts(size):
    from PIL import ImageFont

    try:
        from canvas import _font_faces

        faces = _font_faces()
    except ImportError:
        faces = {}
    fonts = {}
    if faces.get('sans'):
        fonts['sans'] = ImageFont.truetype(faces['sans']['path'], size)
    for candidate in CJK_FONTS:
        try:
            fonts['cjk'] = ImageFont.truetype(candidate, size)
            break
        except OSError:
            continue
    if 'sans' not in fonts:
        try:
            fonts['sans'] = ImageFont.load_default(size)
        except TypeError as error:  # Pillow 10.1 以前没有可缩放的默认字体，改画 SVG
            raise ImportError('Pillow 太旧') from error
    fonts.setdefault('cjk', fonts['sans'])
    return fonts


def _pick(fonts, text):
    return fonts['cjk'] if any(ord(ch) > 0x2E80 for ch in text) else fonts['sans']


def _draw_png(path, panels, axis, footer):
    from PIL import Image, ImageDraw, PngImagePlugin

    height, boxes = _layout(len(panels))
    s = SCALE
    image = Image.new('RGB', (WIDTH * s, height * s), SURFACE)
    draw = ImageDraw.Draw(image)
    small, title = _fonts(13 * s), _fonts(15 * s)
    t_low, t_high, t_ticks, t_labels, t_title = axis
    for (name, (low, high, ticks, labels), lines), box in zip(panels, boxes):
        left, top, right, bottom = box

        def tx(t, left=left, right=right):
            return left + (t - t_low) / (t_high - t_low) * (right - left)

        def ty(v, top=top, bottom=bottom, low=low, high=high):
            return bottom - (v - low) / (high - low) * (bottom - top)

        for t in t_ticks:
            draw.line([(tx(t) * s, top * s), (tx(t) * s, bottom * s)], fill=GRID, width=s)
        for v, text in zip(ticks, labels):
            draw.line([(left * s, ty(v) * s), (right * s, ty(v) * s)], fill=GRID, width=s)
            draw.text(((left - 10) * s, ty(v) * s), text, font=_pick(small, text), fill=MUTED, anchor='rm')
        draw.line([(left * s, top * s), (left * s, bottom * s), (right * s, bottom * s)], fill=AXIS, width=s)
        draw.text((left * s, (top - 10) * s), name, font=_pick(title, name), fill=INK, anchor='ls')
        for (x0, y0), (x1, y1) in lines:
            draw.line([(x0 * s, y0 * s), (x1 * s, y1 * s)], fill=TRACE, width=2 * s)
    bottom = boxes[-1][3]
    for t, text in zip(t_ticks, t_labels):
        x = boxes[-1][0] + (t - t_low) / (t_high - t_low) * (boxes[-1][2] - boxes[-1][0])
        draw.text((x * s, (bottom + 8) * s), text, font=small['sans'], fill=MUTED, anchor='mt')
    draw.text(((LEFT + WIDTH - RIGHT) / 2 * s, (bottom + 30) * s), t_title, font=title['sans'], fill=INK, anchor='mt')
    draw.text((LEFT * s, (height - 12) * s), footer, font=_pick(small, footer), fill=MUTED, anchor='ls')
    image = image.resize((WIDTH, height), Image.Resampling.LANCZOS)
    info = PngImagePlugin.PngInfo()
    info.add_text('Source', footer)
    image.save(path, pnginfo=info, optimize=True)


def _draw_svg(path, panels, axis, footer):
    height, boxes = _layout(len(panels))
    t_low, t_high, t_ticks, t_labels, t_title = axis
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
        f'font-family="{SVG_FONTS}">',
        f'<rect width="100%" height="100%" fill="{SURFACE}"/>',
    ]
    for (name, (low, high, ticks, labels), lines), (left, top, right, bottom) in zip(panels, boxes):
        for t in t_ticks:
            x = left + (t - t_low) / (t_high - t_low) * (right - left)
            out.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="{GRID}"/>')
        for v, text in zip(ticks, labels):
            y = bottom - (v - low) / (high - low) * (bottom - top)
            out.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="{GRID}"/>')
            out.append(
                f'<text x="{left - 10}" y="{y + 4.5:.2f}" font-size="13" fill="{MUTED}" text-anchor="end">'
                f'{escape(text)}</text>'
            )
        out.append(f'<polyline points="{left},{top} {left},{bottom} {right},{bottom}" fill="none" stroke="{AXIS}"/>')
        out.append(f'<text x="{left}" y="{top - 10}" font-size="15" fill="{INK}">{escape(name)}</text>')
        path_data = ''.join(f'M{x0:.2f} {y0:.2f}L{x1:.2f} {y1:.2f}' for (x0, y0), (x1, y1) in lines)
        out.append(f'<path d="{path_data}" fill="none" stroke="{TRACE}" stroke-width="2" stroke-linecap="round"/>')
    left, _, right, bottom = boxes[-1]
    for t, text in zip(t_ticks, t_labels):
        x = left + (t - t_low) / (t_high - t_low) * (right - left)
        out.append(
            f'<text x="{x:.2f}" y="{bottom + 21}" font-size="13" fill="{MUTED}" text-anchor="middle">{text}</text>'
        )
    out.append(
        f'<text x="{(LEFT + WIDTH - RIGHT) / 2}" y="{bottom + 45}" font-size="15" fill="{INK}" '
        f'text-anchor="middle">{escape(t_title)}</text>'
    )
    out.append(f'<text x="{LEFT}" y="{height - 12}" font-size="13" fill="{MUTED}">{escape(footer)}</text>')
    out.append('</svg>\n')
    Path(path).write_text('\n'.join(out), encoding='utf-8', newline='\n')


# ---------------------------------------------------------------- 入口 ----
def _png_available():
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except ImportError:
        return False
    return True


def waveforms(source, folder, name=None, signals=None, start=None, end=None, svg=False):
    """写出 <name>.xlsx（数据 + 统计）和 <name>.png（无 Pillow 或 svg=True 时 .svg），返回摘要。"""
    source, folder = Path(source).resolve(), Path(folder).resolve()
    if start is not None and end is not None and end <= start:
        raise ValueError('结束时间必须大于开始时间')
    header, time, chosen = _columns(source, signals)
    names = [header[i] for i in chosen]
    # 离线预仿真不是 PSIM 结果：输出名带 presim，deliver 不会把它交给客户。
    name = name or ('presim-waveforms' if 'presim' in source.name.lower() else 'waveforms')
    folder.mkdir(parents=True, exist_ok=True)
    workbook_path = folder / f'{name}.xlsx'
    stats = [Stats() for _ in chosen]
    samples, first, last = 0, None, None

    def data():
        nonlocal samples, first, last
        for t, values in _rows(source, time, chosen, start, end):
            samples += 1
            first = t if first is None else first
            last = t
            for stat, value in zip(stats, values):
                stat.add(t, value)
            yield [t, *values]

    workbook = Workbook(workbook_path)
    complete = False
    try:
        rows, sheets = data(), 0
        while True:
            chunk = itertools.islice(rows, MAX_ROWS - 1)
            head = next(chunk, None)
            if head is None and sheets:
                break
            sheets += 1
            title = '波形数据' if sheets == 1 else f'波形数据 {sheets}'
            widths = [16] * (len(names) + 1)
            body = () if head is None else itertools.chain([head], chunk)
            workbook.sheet(title, itertools.chain([[header[time], *names]], body), widths)
            if head is None:
                break
        if samples < 2:
            raise ValueError('时间窗内少于 2 个样本，无法画曲线')
        summary = {n: s.summary() for n, s in zip(names, stats)}
        info = [
            ['项目', '值'],
            ['数据来源', source.name],
            ['采样点数', samples],
            ['开始时间 (s)', first],
            ['结束时间 (s)', last],
            ['说明', '平均值和有效值按时间加权，覆盖上面的整个时间范围（可能含启动过程）；稳态指标请按窗口测量。'],
            [],
            ['信号', '最小值', '最大值', '末值', '平均值', '有效值'],
            *([n, v['min'], v['max'], v['final'], v['mean'], v['rms']] for n, v in summary.items()),
        ]
        workbook.sheet('统计', info, (16, 16, 16, 16, 16, 16), frozen=False)
        complete = True
    finally:
        workbook.close()
        if not complete:
            workbook_path.unlink(missing_ok=True)

    warnings = []
    plotted = names[:MAX_PANELS]
    if len(names) > MAX_PANELS:
        warnings.append(
            f'信号超过 {MAX_PANELS} 个，曲线图只画前 {MAX_PANELS} 个；用 signals 选择要画的信号，表格含全部信号'
        )
    if first == last:
        workbook_path.unlink()
        raise ValueError('时间窗内所有样本的时间相同，无法画曲线')
    for old in (folder / f'{name}.png', folder / f'{name}.svg'):
        old.unlink(missing_ok=True)
    footer = f'Data: {source.name}, {samples} samples. Each pixel column shows the min-max of its samples.'
    t_axis = _time_axis(first, last)
    plot = None
    for scale, draw in ((SCALE, _draw_png), (1, _draw_svg)):
        if draw is _draw_png and (svg or not _png_available()):
            continue
        columns = (WIDTH - LEFT - RIGHT) * scale
        bins = _envelope(source, time, chosen[: len(plotted)], start, end, t_axis[0], t_axis[1], columns)
        _, boxes = _layout(len(plotted))
        panels = []
        for signal, cells, box in zip(plotted, bins, boxes):
            stat = summary[signal]
            if stat['min'] is None:
                warnings.append(f'{signal} 在时间窗内没有数值')
                axis = _value_axis(0.0, 0.0)
            else:
                axis = _value_axis(stat['min'], stat['max'])
            panels.append((signal, axis, _segments(cells, box, axis[0], axis[1])))
        plot = folder / f'{name}.{"png" if draw is _draw_png else "svg"}'
        try:
            draw(plot, panels, t_axis, footer)
            break
        except ImportError:
            plot.unlink(missing_ok=True)
    return {
        'csv': str(source),
        'xlsx': str(workbook_path),
        'plot': str(plot),
        'plot_format': plot.suffix[1:],
        'signals': names,
        'plotted': plotted,
        'samples': samples,
        'time': [first, last],
        'sheets': sheets + 1,
        'summary': summary,
        'source': 'drawn from CSV data with a per-pixel min-max envelope; not a SIMVIEW screenshot',
        'warnings': warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, help='波形 CSV（第一行列名，含 Time 列）')
    parser.add_argument('folder', type=Path, help='输出目录')
    parser.add_argument('--name', help='输出文件名（不含扩展名），默认 waveforms')
    parser.add_argument('--signal', action='append', default=[], help='只画、只导出这些信号，可重复')
    parser.add_argument('--start', type=float, help='开始时间 (s)')
    parser.add_argument('--end', type=float, help='结束时间 (s)')
    parser.add_argument('--svg', action='store_true', help='画 SVG 而不是 PNG')
    args = parser.parse_args(argv)
    try:
        result = waveforms(args.csv, args.folder, args.name, args.signal, args.start, args.end, args.svg)
    except (ValueError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
