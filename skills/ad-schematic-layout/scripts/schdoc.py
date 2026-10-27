"""Altium SchDoc 读写：复合文档（CFB）、记录编码和基础图元写入，只用 Python 标准库。

生成的文件在任何系统上字节一致；保存后仍须用 AD 原生打开、编译和出图确认。
"""

import copy
import hashlib
import math
from pathlib import Path
import struct

FREE = 0xFFFFFFFF
END = 0xFFFFFFFE
FAT_SECTOR = 0xFFFFFFFD
DIFAT_SECTOR = 0xFFFFFFFC
DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))
HEADER = 'Protel for Windows - Schematic Capture Binary File Version 5.0'
SHEET_TEMPLATE = {
    'RECORD': '31',
    'FONTIDCOUNT': '9',
    'SIZE1': '9',
    'FONTNAME1': 'Times New Roman',
    'SIZE2': '8',
    'FONTNAME2': 'Times New Roman',
    'SIZE3': '12',
    'FONTNAME3': 'Times New Roman',
    'SIZE4': '16',
    'FONTNAME4': 'Times New Roman',
    'SIZE5': '11',
    'FONTNAME5': 'Times New Roman',
    'SIZE6': '8',
    'FONTNAME6': 'Times New Roman',
    'SIZE7': '12',
    'FONTNAME7': 'Times New Roman',
    'SIZE8': '9',
    'FONTNAME8': 'Times New Roman',
    'USEMBCS': 'T',
    'ISBOC': 'T',
    'HOTSPOTGRIDON': 'T',
    'HOTSPOTGRIDSIZE': '10',
    'SHEETSTYLE': '3',
    'USECUSTOMSHEET': 'T',
    'SYSTEMFONT': '1',
    'BORDERON': 'F',
    'TITLEBLOCKON': 'F',
    'SHEETNUMBERSPACESIZE': '4',
    'AREACOLOR': '16777215',
    'SNAPGRIDON': 'T',
    'SNAPGRIDSIZE': '10',
    'VISIBLEGRIDON': 'T',
    'VISIBLEGRIDSIZE': '10',
    'CUSTOMX': '5400',
    'CUSTOMY': '4200',
    'CUSTOMXZONES': '6',
    'CUSTOMYZONES': '5',
    'CUSTOMMARGINWIDTH': '20',
    'DISPLAY_UNIT': '4',
    'REFERENCEZONESON': 'F',
    'SIZE9': '12',
    'FONTNAME9': 'SimSun',
}


# ---------------------------------------------------------------- 复合文档 ----


def read_compound(source):
    """读取复合文档中的全部流，返回 {'目录/流名': bytes}。"""
    raw = Path(source).read_bytes() if not isinstance(source, (bytes, bytearray)) else bytes(source)
    if raw[:8] != bytes.fromhex('D0CF11E0A1B11AE1'):
        raise ValueError('不是复合文档（CFB）')
    sector_size = 1 << struct.unpack_from('<H', raw, 30)[0]
    mini_size = 1 << struct.unpack_from('<H', raw, 32)[0]
    fat_count, dir_start = struct.unpack_from('<II', raw, 44)[0], struct.unpack_from('<I', raw, 48)[0]
    cutoff, minifat_start, minifat_count = struct.unpack_from('<III', raw, 56)
    difat_start, difat_count = struct.unpack_from('<II', raw, 68)

    def sector(index):
        start = (index + 1) * sector_size
        if start >= len(raw):
            raise ValueError('复合文档扇区越界')
        return raw[start : start + sector_size]

    fat_sectors = list(struct.unpack_from('<109I', raw, 76))
    per_sector = sector_size // 4
    next_difat = difat_start
    for _ in range(difat_count):
        if next_difat in (END, FREE):
            break
        values = struct.unpack(f'<{per_sector}I', sector(next_difat))
        fat_sectors.extend(values[:-1])
        next_difat = values[-1]
    fat = []
    for index in fat_sectors[:fat_count]:
        fat.extend(struct.unpack(f'<{per_sector}I', sector(index)))

    def chain(start, table, limit):
        seen, result = set(), []
        while start not in (END, FREE) and start < limit:
            if start in seen:
                raise ValueError('复合文档扇区链成环')
            seen.add(start)
            result.append(start)
            start = table[start]
        return result

    def read_chain(start, size=None):
        data = b''.join(sector(i) for i in chain(start, fat, len(fat)))
        return data if size is None else data[:size]

    directory = read_chain(dir_start)
    entries = []
    for offset in range(0, len(directory), 128):
        item = directory[offset : offset + 128]
        name_size = struct.unpack_from('<H', item, 64)[0]
        name = item[: max(0, name_size - 2)].decode('utf-16le', errors='replace')
        kind = item[66]
        left, right, child = struct.unpack_from('<III', item, 68)
        start, size = struct.unpack_from('<IQ', item, 116)
        entries.append(
            {'name': name, 'kind': kind, 'left': left, 'right': right, 'child': child, 'start': start, 'size': size}
        )
    if not entries or entries[0]['kind'] != 5:
        raise ValueError('复合文档缺少根目录')
    root = entries[0]
    mini_stream = read_chain(root['start'], root['size'])
    minifat = []
    if minifat_count:
        table = read_chain(minifat_start)
        minifat = list(struct.unpack(f'<{len(table) // 4}I', table))

    def stream(entry):
        if entry['size'] < cutoff:
            data = b''.join(
                mini_stream[i * mini_size : (i + 1) * mini_size] for i in chain(entry['start'], minifat, len(minifat))
            )
            return data[: entry['size']]
        return read_chain(entry['start'], entry['size'])

    streams = {}

    def walk(index, prefix, depth=0):
        if index == FREE or index >= len(entries) or depth > 64:
            return
        entry = entries[index]
        walk(entry['left'], prefix, depth + 1)
        walk(entry['right'], prefix, depth + 1)
        path = prefix + entry['name']
        if entry['kind'] == 2:
            streams[path] = stream(entry)
        elif entry['kind'] == 1:
            walk(entry['child'], path + '/', depth + 1)

    walk(root['child'], '')
    return streams


def write_compound(path, streams):
    """写出只含根目录下若干流的标准复合文档（含小流分配表）。"""
    names = sorted(streams, key=lambda n: (len(n), n.upper()))
    if any('/' in name for name in names):
        raise ValueError('写入器只支持根目录下的流')
    sectors, links = [], []

    def allocate(data):
        first = len(sectors)
        count = math.ceil(len(data) / 512)
        for i in range(count):
            sectors.append(data[i * 512 : (i + 1) * 512].ljust(512, b'\x00'))
            links.append(first + i + 1 if i + 1 < count else END)
        return first if count else END

    starts, mini_data, mini_links = {}, b'', []
    for name in names:
        value = streams[name]
        if len(value) >= 4096:
            starts[name] = allocate(value)
        elif value:
            starts[name] = len(mini_links)
            count = math.ceil(len(value) / 64)
            first = len(mini_links)
            mini_links.extend(first + i + 1 if i + 1 < count else END for i in range(count))
            mini_data += value.ljust(count * 64, b'\x00')
        else:
            starts[name] = END
    mini_start = allocate(mini_data)
    mini_table = b''.join(struct.pack('<I', x) for x in mini_links)
    mini_table = mini_table.ljust(math.ceil(len(mini_table) / 512) * 512, b'\xff')
    mini_fat_start = allocate(mini_table)
    left, right = {}, {}

    def tree(indices):
        if not indices:
            return FREE
        mid = len(indices) // 2
        item = indices[mid]
        left[item] = tree(indices[:mid])
        right[item] = tree(indices[mid + 1 :])
        return item

    child = tree(list(range(1, len(names) + 1)))

    def entry(name, kind, start, size, index=0):
        data = bytearray(128)
        title = (name + '\x00').encode('utf-16le')
        if len(title) > 64:
            raise ValueError(f'流名过长：{name}')
        data[: len(title)] = title
        struct.pack_into(
            '<HBBIII',
            data,
            64,
            len(title),
            kind,
            1,
            left.get(index, FREE),
            right.get(index, FREE),
            child if kind == 5 else FREE,
        )
        struct.pack_into('<IQ', data, 116, start, size)
        return bytes(data)

    directory = entry('Root Entry', 5, mini_start, len(mini_data))
    for i, name in enumerate(names, 1):
        directory += entry(name, 2, starts[name], len(streams[name]), i)
    # 未使用的目录项全零，但左右兄弟和子节点须为 NOSTREAM。
    unused = bytearray(128)
    struct.pack_into('<III', unused, 68, FREE, FREE, FREE)
    directory += bytes(unused) * (-len(directory) // 128 % 4)
    directory_start = allocate(directory)
    fat_count = 1
    while math.ceil((len(sectors) + fat_count) / 128) > fat_count:
        fat_count += 1
    if fat_count > 109:
        raise ValueError('文档过大，超出写入器支持范围')
    fat_ids = list(range(len(sectors), len(sectors) + fat_count))
    fat = links + [FAT_SECTOR] * fat_count
    fat += [FREE] * (fat_count * 128 - len(fat))
    for i in range(fat_count):
        sectors.append(struct.pack('<128I', *fat[i * 128 : (i + 1) * 128]))
    header = bytearray(512)
    header[:8] = bytes.fromhex('D0CF11E0A1B11AE1')
    struct.pack_into('<HHHHH', header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into(
        '<IIIIIIIII', header, 40, 0, fat_count, directory_start, 0, 4096, mini_fat_start, len(mini_table) // 512, END, 0
    )
    struct.pack_into('<109I', header, 76, *(fat_ids + [FREE] * (109 - fat_count)))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + b''.join(sectors))


# ------------------------------------------------------------------ 记录 ----


def encode(record):
    """把一条属性记录编码为文本记录（长度前缀 + GBK 文本 + 结尾 0）。"""
    text = '|' + '|'.join(f'{k}={v}' for k, v in record.items())
    raw = text.encode('gbk') + b'\x00'
    return struct.pack('<I', len(raw)) + raw


def _text(raw, utf8=False):
    if utf8:
        return raw.decode('utf-8', errors='replace')
    # 普通记录由本写入器按 GBK 编码；UTF-8 属性有显式的 %UTF8% 前缀。
    # 部分合法 GBK 字节也恰好是合法 UTF-8，不能优先按 UTF-8 猜测。
    for codec in ('gbk', 'utf-8'):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return raw.decode('cp1252', errors='replace')


def _properties(raw):
    record = {}
    for field in raw.split(b'|'):
        if b'=' not in field:
            continue
        key, value = field.split(b'=', 1)
        key = key.decode('ascii', errors='replace').upper()
        if key.startswith('%UTF8%'):
            record[key[6:]] = _text(value, utf8=True)
        elif key not in record:
            record[key] = _text(value)
    return record


def _binary_pin(raw):
    """解码 AD 保存的二进制引脚记录，转为与文本记录相同的属性。"""
    offset = 0

    def take(fmt):
        nonlocal offset
        values = struct.unpack_from(fmt, raw, offset)
        offset += struct.calcsize(fmt)
        return values

    def pascal():
        nonlocal offset
        size = raw[offset]
        value = _text(raw[offset + 1 : offset + 1 + size])
        offset += 1 + size
        return value

    kind, _, part, mode, inner, outer, inside, outside = take('<IBhBBBBB')
    if kind != 2:
        raise ValueError(f'未知二进制记录类型 {kind}')
    description = pascal()
    formal, electrical, flags, length, x, y, color = take('<BBBhhhI')
    name, designator = pascal(), pascal()
    return {
        'RECORD': '2',
        'OWNERPARTID': str(part),
        'OWNERPARTDISPLAYMODE': str(mode),
        'SYMBOL_INNEREDGE': str(inner),
        'SYMBOL_OUTEREDGE': str(outer),
        'SYMBOL_INSIDE': str(inside),
        'SYMBOL_OUTSIDE': str(outside),
        'DESCRIPTION': description,
        'FORMALTYPE': str(formal),
        'ELECTRICAL': str(electrical),
        'PINCONGLOMERATE': str(flags),
        'PINLENGTH': str(length),
        'LOCATION.X': str(x),
        'LOCATION.Y': str(y),
        'COLOR': str(color),
        'NAME': name,
        'DESIGNATOR': designator,
    }


def decode_records(raw):
    """解析 FileHeader 或库 Data 流：文本记录和二进制引脚记录都转为属性字典。"""
    records, offset, owner = [], 0, None
    while offset + 4 <= len(raw):
        header = struct.unpack_from('<I', raw, offset)[0]
        size, kind = header & 0xFFFFFF, header >> 24
        offset += 4
        if size == 0:
            break
        if offset + size > len(raw):
            raise ValueError('记录长度超出流范围')
        body = raw[offset : offset + size]
        offset += size
        if kind == 0:
            record = _properties(body.rstrip(b'\x00'))
        elif kind == 1:
            record = _binary_pin(body)
            if owner is not None:
                record['OWNERINDEX'] = str(owner - 1)
        else:
            raise ValueError(f'未知记录类型 {kind}')
        if record.get('RECORD') == '1':
            owner = len(records)
        records.append(record)
    return records


def read(path):
    """读取 SchDoc 的全部记录（首条为文件头，第二条为图纸）。"""
    streams = read_compound(path)
    if 'FileHeader' not in streams:
        raise ValueError('不是 SchDoc：缺少 FileHeader 流')
    return decode_records(streams['FileHeader'])


def point(record, prefix='LOCATION'):
    def value(axis):
        whole = float(record.get(f'{prefix}.{axis}', 0))
        return whole + float(record.get(f'{prefix}.{axis}_FRAC', 0)) / 100000

    return value('X'), value('Y')


def pin_end(record):
    x, y = point(record)
    dx, dy = DIRECTIONS[int(record['PINCONGLOMERATE']) & 3]
    size = float(record.get('PINLENGTH', 0))
    return x + dx * size, y + dy * size


# ---------------------------------------------------------------- 写图元 ----


class Sheet:
    """按记录顺序累积图元；坐标单位 10 mil，y 向上。"""

    def __init__(self, size=(5400, 4200)):
        self.records = [{'HEADER': HEADER, 'WEIGHT': '1'}, copy.deepcopy(SHEET_TEMPLATE)]
        # 分区数随图幅变化，小图纸不挤满 6×5 的分区标记。
        self.records[1].update(
            CUSTOMX=str(size[0]),
            CUSTOMY=str(size[1]),
            CUSTOMXZONES=str(min(8, max(2, round(size[0] / 100)))),
            CUSTOMYZONES=str(min(6, max(2, round(size[1] / 100)))),
        )
        self.pins = {}

    def add(self, kind, **values):
        row = {'RECORD': str(kind)}
        row.update({k: str(round(v) if isinstance(v, float) else v) for k, v in values.items()})
        self.records.append(row)
        return len(self.records) - 1

    def font_size(self, font):
        return float(self.records[1].get(f'SIZE{font}', 9))

    def text(self, x, y, text, font=1, color=8388608, owner=None):
        values = {
            'LOCATION.X': round(x, 3),
            'LOCATION.Y': round(y, 3),
            'COLOR': color,
            'FONTID': font,
            'TEXT': text,
            'OWNERPARTID': -1,
        }
        if owner is not None:
            values.update(OWNERINDEX=owner - 1, OWNERPARTID=1)
        return self.add(4, **values)

    def wire(self, *points, width=1, color=8388608):
        if len(points) < 2:
            raise ValueError('导线至少需要两个点')
        for a, b in zip(points, points[1:]):
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f'非正交导线：{a} -> {b}')
        values = {'LINEWIDTH': width, 'COLOR': color, 'LOCATIONCOUNT': len(points)}
        for i, (x, y) in enumerate(points, 1):
            values[f'X{i}'] = round(x, 3)
            values[f'Y{i}'] = round(y, 3)
        return self.add(27, **values)

    def line(self, a, b, owner=None, color=128, width=1):
        values = {
            'LINEWIDTH': width,
            'COLOR': color,
            'LOCATIONCOUNT': 2,
            'X1': a[0],
            'Y1': a[1],
            'X2': b[0],
            'Y2': b[1],
        }
        if owner is not None:
            values.update(OWNERINDEX=owner - 1, OWNERPARTID=1, OWNERPARTDISPLAYMODE=0, ISNOTACCESIBLE='T')
        return self.add(6, **values)

    def rect(self, x1, y1, x2, y2, owner=None, fill=False, width=1):
        values = {
            'LOCATION.X': x1,
            'LOCATION.Y': y1,
            'CORNER.X': x2,
            'CORNER.Y': y2,
            'LINEWIDTH': width,
            'COLOR': 128,
            'OWNERPARTID': -1,
        }
        if fill:
            values.update(AREACOLOR=11599871, ISSOLID='T')
        if owner is not None:
            values.update(OWNERINDEX=owner - 1, OWNERPARTID=1, OWNERPARTDISPLAYMODE=0, ISNOTACCESIBLE='T')
        return self.add(14, **values)

    def label(self, x, y, text, orientation=0):
        return self.add(
            25,
            INDEXINSHEET=-1,
            OWNERPARTID=-1,
            **{'LOCATION.X': x, 'LOCATION.Y': y, 'COLOR': 128, 'FONTID': 1, 'TEXT': text, 'ORIENTATION': orientation},
        )

    def junction(self, p):
        return self.add(
            29, INDEXINSHEET=-1, OWNERPARTID=-1, **{'LOCATION.X': p[0], 'LOCATION.Y': p[1], 'COLOR': 8388608}
        )

    def power(self, x, y, name, ground=False):
        return self.add(
            17,
            INDEXINSHEET=-1,
            OWNERPARTID=-1,
            STYLE=4 if ground else 2,
            SHOWNETNAME='T',
            **{'LOCATION.X': x, 'LOCATION.Y': y, 'ORIENTATION': 3 if ground else 1, 'COLOR': 128, 'TEXT': name},
        )

    def _part(self, ref, library, x, y, **extra):
        return self.add(
            1,
            LIBREFERENCE=library,
            PARTCOUNT=2,
            DISPLAYMODECOUNT=1,
            OWNERPARTID=-1,
            **{
                'LOCATION.X': x,
                'LOCATION.Y': y,
                'ORIENTATION': 0,
                'CURRENTPARTID': 1,
                'LIBRARYPATH': '*',
                'SOURCELIBRARYNAME': '*',
                'SHEETPARTFILENAME': '*',
                'TARGETFILENAME': '*',
                'UNIQUEID': hashlib.sha256(ref.encode()).hexdigest()[:8].upper(),
            },
            **extra,
        )

    def _part_text(self, owner, ref, value, des_pos, comment_pos, font):
        for record, pos, text, name in ((34, des_pos, ref, 'Designator'), (41, comment_pos, value, 'Comment')):
            extra = {'READONLYSTATE': 1} if record == 34 else {}
            self.add(
                record,
                OWNERINDEX=owner - 1,
                INDEXINSHEET=-1,
                OWNERPARTID=-1,
                **{
                    'LOCATION.X': pos[0],
                    'LOCATION.Y': pos[1],
                    'COLOR': 8388608,
                    'FONTID': font,
                    'TEXT': text,
                    'NAME': name,
                },
                **extra,
            )

    def component(self, ref, name, body, pins, comment=None, comment_pos=None, des_pos=None, pin_length=20, font=1):
        """矩形符号器件；pins 为 (编号, 名称, x, y, 方向, 电气类型)，x/y 在框边。"""
        x1, y1, x2, y2 = body
        idx = self._part(
            ref, name, (x1 + x2) / 2, (y1 + y2) / 2, AREACOLOR=11599871, COLOR=128, PARTIDLOCKED='F', DESIGNITEMID=name
        )
        self.rect(*body, owner=idx, fill=True)
        self.pins[ref] = {}
        for number, pin_name, x, y, direction, electrical in pins:
            dx, dy = DIRECTIONS[direction]
            self.add(
                2,
                OWNERINDEX=idx - 1,
                OWNERPARTID=1,
                FORMALTYPE=1,
                ELECTRICAL=electrical,
                PINCONGLOMERATE=56 + direction,
                PINLENGTH=pin_length,
                **{
                    'LOCATION.X': x,
                    'LOCATION.Y': y,
                    'NAME': pin_name,
                    'DESIGNATOR': number,
                    'SWAPIDPART': 1,
                    'COLOR': 0,
                },
            )
            self.pins[ref][str(number)] = (x + dx * pin_length, y + dy * pin_length)
        # 位号在框上方、注释在框下方，不压框线和引脚名。
        height = self.font_size(font)
        self._part_text(idx, ref, comment or name, des_pos or (x1, y2 + 3), comment_pos or (x1, y1 - 3 - height), font)
        return idx

    def passive(
        self, ref, value, x, y, vertical=False, kind='R', scale=0.5, grid=10, font=1, des_pos=None, comment_pos=None
    ):
        """按比例绘制两脚无源件；引脚热端始终落在栅格上，文字保持完整字高。"""
        s = scale
        reach = round(20 * s)
        hot = max(grid, round(32 * s / grid) * grid)
        if hot - reach < 2:
            hot += grid
        length = hot - reach

        def at(u, v):
            # u 沿引脚轴向，v 为横向；竖放时轴向朝上。
            return (x - v, y + u) if vertical else (x + u, y + v)

        idx = self._part(ref, kind, x, y, COLOR=128, DESIGNITEMID=kind)
        self.pins[ref] = {}
        # 横放时 1 脚在左，竖放时 1 脚在上。
        ends = ((1, '1', 1), (-1, '2', 3)) if vertical else ((-1, '1', 2), (1, '2', 0))
        for sign, number, direction in ends:
            px, py = at(sign * reach, 0)
            self.add(
                2,
                OWNERINDEX=idx - 1,
                OWNERPARTID=1,
                FORMALTYPE=1,
                ELECTRICAL=4,
                PINCONGLOMERATE=32 + direction,
                PINLENGTH=length,
                **{
                    'LOCATION.X': px,
                    'LOCATION.Y': py,
                    'NAME': number,
                    'DESIGNATOR': number,
                    'SWAPIDPART': 1,
                    'COLOR': 0,
                },
            )
            self.pins[ref][number] = at(sign * hot, 0)
        if kind == 'C':
            gap, plate = max(2, round(4 * s)), round(14 * s)
            for u in (-gap, gap):
                self.line(at(u, -plate), at(u, plate), owner=idx)
            self.line(at(-reach, 0), at(-gap, 0), owner=idx)
            self.line(at(reach, 0), at(gap, 0), owner=idx)
            half = plate
        elif kind == 'L':
            points = []
            for center in (-15, -5, 5, 15):
                for i in range(9):
                    angle = math.pi * (1 - i / 8)
                    points.append(
                        tuple(round(v) for v in at(s * (center + 5 * math.cos(angle)), s * 6 * math.sin(angle)))
                    )
            values = {
                'OWNERINDEX': idx - 1,
                'OWNERPARTID': 1,
                'OWNERPARTDISPLAYMODE': 0,
                'ISNOTACCESIBLE': 'T',
                'LINEWIDTH': 1,
                'COLOR': 8388608,
                'LOCATIONCOUNT': len(points),
            }
            for i, (px, py) in enumerate(points, 1):
                values[f'X{i}'] = px
                values[f'Y{i}'] = py
            self.add(6, **values)
            half = round(6 * s)
        elif kind == 'Y':
            box, plate, bar = round(9 * s), round(14 * s), round(17 * s)
            (ax, ay), (bx, by) = at(-box, -round(13 * s)), at(box, round(13 * s))
            self.rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), owner=idx)
            for u in (-plate, plate):
                self.line(at(u, -bar), at(u, bar), owner=idx)
                self.line(at(u, 0), at(reach if u > 0 else -reach, 0), owner=idx)
            half = bar
        else:
            half = max(2, round(6 * s))
            (ax, ay), (bx, by) = at(-reach, -half), at(reach, half)
            self.rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), owner=idx)
        height = self.font_size(font)
        if vertical:
            des_pos = des_pos or (x + half + 3, y + 1)
            comment_pos = comment_pos or (x + half + 3, y - 1 - height)
        else:
            des_pos = des_pos or (x - reach, y + half + 2 + round(1.1 * height))
            comment_pos = comment_pos or (x - reach, y + half + 1)
        self._part_text(idx, ref, value, des_pos, comment_pos, font)
        return idx

    def save(self, path):
        self.records[0]['WEIGHT'] = str(len(self.records) - 1)
        header = b''.join(encode(record) for record in self.records)
        write_compound(
            path,
            {
                'FileHeader': header,
                'Storage': encode({'HEADER': 'Icon storage'}),
                'Additional': encode({'HEADER': HEADER}),
            },
        )
        if read(path) != self.records:
            raise RuntimeError('保存后读回的记录与写入不一致')
        return Path(path)
