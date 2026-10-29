"""把波形 CSV 画成曲线图并转成 Excel 表：PNG 需要 Pillow，没有时写 SVG；XLSX 只用标准库写出。

Excel 表是 CSV 的逐格副本：表头、每一行、每一列和数字原文都不改，写完读回逐格核对，有一格不同就报错。
曲线每个信号一栏，共用时间轴；每个像素列画该列全部样本的最小到最大值（包络），长波形里的尖峰和振荡不会被抽稀掉。
曲线是按 CSV 数据绘制的结果图，不是 SIMVIEW 截图。
"""

import argparse
import csv
from html import escape
import itertools
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

MAX_ROWS = 1_048_576  # Excel 每张表的行数上限（含表头）
MAX_COLUMNS = 16_384  # Excel 每张表的列数上限
MAX_TEXT = 32_767  # Excel 单元格的字符数上限
NUMBER = re.compile(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')  # XML 里不能出现的字符
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


def _encoding(path):
    """CSV 编码：UTF-8（可带 BOM）；不是就按 GB18030 读（中文 Excel 另存的 CSV）。"""
    for choice in ('utf-8-sig', 'gb18030'):
        try:
            with open(path, encoding=choice) as stream:
                while stream.read(1 << 20):
                    pass
        except UnicodeDecodeError:
            continue
        return choice
    raise ValueError('CSV 编码无法识别（支持 UTF-8 和 GB18030）')


def _columns(path, signals, encoding='utf-8-sig'):
    with open(path, newline='', encoding=encoding) as stream:
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


def _rows(path, time, chosen, start, end, encoding='utf-8-sig'):
    """逐行给出 (时间, 各信号值)；跳过时间窗外的行。整个文件的时间都须是有限数值且不递减。"""
    previous = None
    with open(path, newline='', encoding=encoding) as stream:
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
    f'{XML}<styleSheet xmlns="{NS}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/>'
    '</fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle '
    'name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
)


def _letters(index):
    name = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _column(reference):
    """单元格引用的列号（从 0 起）：'AB12' → 27。"""
    number = 0
    for ch in reference:
        if not ch.isalpha():
            break
        number = number * 26 + ord(ch.upper()) - 64
    return number - 1


def _as_cell(text, line):
    """CSV 单元格 → None（空）、('n', 数字原文) 或 ('s', 原文字)。数字照抄原文，Excel 读到的数与 CSV 相同。"""
    if text == '':
        return None
    if len(text) > MAX_TEXT or CONTROL.search(text):
        raise ValueError(f'CSV 第 {line} 行有超过 Excel 字数上限或 XML 不允许的字符，无法原样写进 Excel')
    literal = text.strip()
    if NUMBER.fullmatch(literal) and math.isfinite(float(literal)):
        return 'n', literal.removeprefix('+')
    return 's', text


def _csv_cells(path, encoding):
    """CSV 原样逐行给出单元格列表：第 1 行是表头；空行是空列表，在表里也占一行。"""
    with open(path, newline='', encoding=encoding) as stream:
        for line, row in enumerate(csv.reader(stream), 1):
            if len(row) > MAX_COLUMNS:
                raise ValueError(f'CSV 第 {line} 行超过 Excel 的 {MAX_COLUMNS} 列上限')
            cells = [_as_cell(text, line) for text in row]
            while cells and cells[-1] is None:
                cells.pop()
            yield cells


def _cell_xml(reference, cell):
    kind, text = cell
    if kind == 'n':
        return f'<c r="{reference}"><v>{text}</v></c>'
    text = escape(text, quote=False).replace('\r', '&#13;')  # 裸 \r 会被 XML 解析成 \n
    return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _titles(stem):
    """表名用 CSV 文件名（和 Excel 直接打开 CSV 时一样）；超过行数上限时接着写「名字 (2)」……"""
    base = re.sub(r'[\[\]:*?/\\]', '_', stem).strip("'") or 'Sheet1'
    if base.casefold() == 'history':  # Excel 保留的表名
        base += '_'
    for number in itertools.count(1):
        suffix = '' if number == 1 else f' ({number})'
        yield base[: 31 - len(suffix)] + suffix


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

    def sheet(self, title, rows, width):
        """rows 逐行给出单元格列表，第一行是表头（冻结在顶部）；空列表只占一个行号。"""
        number = len(self.sheets) + 1
        self.sheets.append(title)
        letters = [_letters(i) for i in range(width)]
        columns = f'<cols><col min="1" max="{width}" width="16" customWidth="1"/></cols>' if width else ''
        with self._open(f'xl/worksheets/sheet{number}.xml') as stream:
            stream.write(
                f'{XML}<worksheet xmlns="{NS}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" '
                f'topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>{columns}'
                '<sheetData>'.encode()
            )
            for line, row in enumerate(rows, 1):
                while len(letters) < len(row):
                    letters.append(_letters(len(letters)))
                cells = ''.join(_cell_xml(f'{letters[i]}{line}', c) for i, c in enumerate(row) if c is not None)
                if cells:
                    stream.write(f'<row r="{line}">{cells}</row>'.encode())
            stream.write(b'</sheetData></worksheet>')

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


def copy_to_workbook(source, target, encoding='utf-8-sig'):
    """把 CSV 逐格写进 XLSX；行数超过 Excel 上限时接着写下一张表，每张表都带表头。返回表名列表。"""
    rows = _csv_cells(source, encoding)
    header = next(rows, [])
    titles = _titles(Path(source).stem)
    book = Workbook(target)
    try:
        while True:
            chunk = itertools.islice(rows, MAX_ROWS - 1)
            first = next(chunk, None)
            if first is None and book.sheets:
                break
            body = () if first is None else itertools.chain([first], chunk)
            book.sheet(next(titles), itertools.chain([header], body), len(header))
            if first is None:
                break
    finally:
        book.close()
    return list(book.sheets)


def _expected_rows(source, encoding):
    """按 copy_to_workbook 的分表规则，给出每张表应有的 (表序号, 行号, 单元格)，跳过空行。"""
    rows = _csv_cells(source, encoding)
    header = next(rows, [])
    current = -1
    for number, cells in enumerate(rows):
        sheet, line = divmod(number, MAX_ROWS - 1)
        if sheet != current:
            current = sheet
            if header:
                yield sheet, 1, header
        if cells:
            yield sheet, line + 2, cells
    if current < 0 and header:
        yield 0, 1, header


def _workbook_rows(path):
    """只用标准库读回 XLSX：按表的顺序逐行给出 (表序号, 行号, 单元格)，跳过空行。"""
    with zipfile.ZipFile(path) as archive:
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        links = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {link.get('Id'): link.get('Target') for link in links}
        for index, sheet in enumerate(book.find(f'{{{NS}}}sheets')):
            target = targets[sheet.get(f'{{{REL}}}id')]
            with archive.open(target.lstrip('/') if target.startswith('/') else f'xl/{target}') as stream:
                data = None
                for event, element in ET.iterparse(stream, ('start', 'end')):
                    if event == 'start':
                        data = element if element.tag == f'{{{NS}}}sheetData' else data
                        continue
                    if element.tag != f'{{{NS}}}row':
                        continue
                    cells = []
                    for cell in element.iter(f'{{{NS}}}c'):
                        kind, value = cell.get('t', 'n'), cell.find(f'{{{NS}}}v')
                        if kind == 'inlineStr':
                            value = ('s', ''.join(t.text or '' for t in cell.iter(f'{{{NS}}}t')))
                        elif kind == 'n':
                            value = None if value is None else ('n', value.text)
                        else:
                            raise ValueError(f'Excel 表里有不该出现的单元格类型：{kind}')
                        column = _column(cell.get('r'))
                        cells.extend([None] * (column + 1 - len(cells)))
                        cells[column] = value
                    while cells and cells[-1] is None:
                        cells.pop()
                    if cells:
                        yield index, int(element.get('r')), cells
                    if data is not None:
                        data.clear()  # 读过的行不留在内存里


def verify_workbook(source, workbook, encoding=None):
    """读回 XLSX 与 CSV 逐格对照：表头、行列位置、数字原文和文字都要相同；有一格不同就报错。"""
    encoding = encoding or _encoding(source)
    rows = cells = width = 0
    for want, got in itertools.zip_longest(_expected_rows(source, encoding), _workbook_rows(workbook)):
        if want != got:
            sheet, line, _ = want or got
            raise ValueError(f'Excel 表与 CSV 不一致：第 {sheet + 1} 张表第 {line} 行')
        rows += want[1] != 1
        cells += sum(cell is not None for cell in want[2])
        width = max(width, len(want[2]))
    return {'identical': True, 'data_rows': rows, 'columns': width, 'cells': cells}


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


def _envelope(path, time, chosen, start, end, low, high, columns, encoding='utf-8-sig'):
    """每个像素列记录 (首值, 最小, 最大, 末值)。"""
    bins = [[None] * columns for _ in chosen]
    span = high - low
    for t, values in _rows(path, time, chosen, start, end, encoding):
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
    """写出 <name>.xlsx（CSV 的逐格副本）和 <name>.png（无 Pillow 或 svg=True 时 .svg），返回摘要。

    signals、start、end 只决定曲线和 summary 用哪些信号、哪段时间；Excel 表总是 CSV 的全部内容。
    """
    source, folder = Path(source).resolve(), Path(folder).resolve()
    if start is not None and end is not None and end <= start:
        raise ValueError('结束时间必须大于开始时间')
    encoding = _encoding(source)
    header, time, chosen = _columns(source, signals, encoding)
    names = [header[i] for i in chosen]
    stats = [Stats() for _ in chosen]
    samples, first, last = 0, None, None
    for t, values in _rows(source, time, chosen, start, end, encoding):
        samples += 1
        first = t if first is None else first
        last = t
        for stat, value in zip(stats, values):
            stat.add(t, value)
    if samples < 2:
        raise ValueError('时间窗内少于 2 个样本，无法画曲线')
    if first == last:
        raise ValueError('时间窗内所有样本的时间相同，无法画曲线')
    summary = {n: s.summary() for n, s in zip(names, stats)}

    # 离线预仿真不是 PSIM 结果：输出名带 presim，deliver 不会把它交给客户。
    name = name or ('presim-waveforms' if 'presim' in source.name.lower() else 'waveforms')
    folder.mkdir(parents=True, exist_ok=True)
    workbook_path = folder / f'{name}.xlsx'
    try:
        sheets = copy_to_workbook(source, workbook_path, encoding)
        check = verify_workbook(source, workbook_path, encoding)
    except BaseException:
        workbook_path.unlink(missing_ok=True)
        raise

    warnings = []
    plotted = names[:MAX_PANELS]
    if len(names) > MAX_PANELS:
        warnings.append(
            f'信号超过 {MAX_PANELS} 个，曲线图只画前 {MAX_PANELS} 个；用 signals 选择要画的信号，表格含全部信号'
        )
    for old in (folder / f'{name}.png', folder / f'{name}.svg'):
        old.unlink(missing_ok=True)
    footer = f'Data: {source.name}, {samples} samples. Each pixel column shows the min-max of its samples.'
    t_axis = _time_axis(first, last)
    plot = None
    for scale, draw in ((SCALE, _draw_png), (1, _draw_svg)):
        if draw is _draw_png and (svg or not _png_available()):
            continue
        columns = (WIDTH - LEFT - RIGHT) * scale
        bins = _envelope(source, time, chosen[: len(plotted)], start, end, t_axis[0], t_axis[1], columns, encoding)
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
        'xlsx_check': dict(check, sheets=sheets),
        'plot': str(plot),
        'plot_format': plot.suffix[1:],
        'signals': names,
        'plotted': plotted,
        'samples': samples,
        'time': [first, last],
        'sheets': sheets,
        'summary': summary,
        'source': 'drawn from CSV data with a per-pixel min-max envelope; not a SIMVIEW screenshot',
        'warnings': warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, help='波形 CSV（第一行列名，含 Time 列）')
    parser.add_argument('folder', type=Path, help='输出目录')
    parser.add_argument('--name', help='输出文件名（不含扩展名），默认 waveforms')
    parser.add_argument(
        '--signal', action='append', default=[], help='只画这些信号（Excel 表总是 CSV 的全部内容），可重复'
    )
    parser.add_argument('--start', type=float, help='曲线和统计的开始时间 (s)')
    parser.add_argument('--end', type=float, help='曲线和统计的结束时间 (s)')
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
