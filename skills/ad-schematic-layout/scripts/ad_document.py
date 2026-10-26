"""原生 SchDoc 基础图元写入；保存后必须通过 AD 原生检查。"""
from pathlib import Path
import struct
import math
import hashlib
import copy
try:
    import olefile
except ImportError:
    olefile = None

FREE = 0xffffffff
END = 0xfffffffe
FAT_SECTOR = 0xfffffffd


def encode(record):
    text = '|' + '|'.join(f'{k}={v}' for k, v in record.items())
    raw = text.encode('gbk') + b'\x00'
    return struct.pack('<I', len(raw)) + raw


def read(path):
    if olefile is None:
        raise RuntimeError('读取已有二进制文档需要 olefile；创建不需要此依赖')
    with olefile.OleFileIO(path) as ole:
        raw = ole.openstream('FileHeader').read()
    records = []
    offset = 0
    while offset + 4 <= len(raw):
        size = struct.unpack_from('<I', raw, offset)[0]
        offset += 4
        if size == 0:
            break
        assert offset + size <= len(raw)
        value = raw[offset:offset + size].rstrip(b'\x00').decode('gbk')
        records.append(dict(s.split('=', 1) for s in value.split('|') if '=' in s))
        offset += size
    return records


def write_compound(path, streams):
    """写入标准 CFB，包括小流分配表；不依赖外部库或缓存路径。"""
    names = sorted(streams, key=lambda n: (len(n), n.upper()))
    sectors = []
    links = []

    def allocate(data):
        first = len(sectors)
        count = math.ceil(len(data) / 512)
        for i in range(count):
            sectors.append(data[i * 512:(i + 1) * 512].ljust(512, b'\x00'))
            links.append(first + i + 1 if i + 1 < count else END)
        return first if count else END

    starts = {}
    mini_data = b''
    mini_links = []
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
    left = {}
    right = {}

    def tree(indices):
        if not indices:
            return FREE
        mid = len(indices) // 2
        item = indices[mid]
        left[item] = tree(indices[:mid])
        right[item] = tree(indices[mid + 1:])
        return item

    child = tree(list(range(1, len(names) + 1)))

    def entry(name, typ, start, size, index=0):
        raw = bytearray(128)
        title = (name + '\x00').encode('utf-16le')
        assert len(title) <= 64
        raw[:len(title)] = title
        struct.pack_into('<HBBIII', raw, 64, len(title), typ, 1,
                         left.get(index, FREE), right.get(index, FREE), child if typ == 5 else FREE)
        struct.pack_into('<IQ', raw, 116, start, size)
        return bytes(raw)

    directory = entry('Root Entry', 5, mini_start, len(mini_data))
    for i, name in enumerate(names, 1):
        directory += entry(name, 2, starts[name], len(streams[name]), i)
    # 未使用的目录项按 CFB 规范全零，但左右兄弟和子节点须为 NOSTREAM。
    unused = bytearray(128)
    struct.pack_into('<III', unused, 68, FREE, FREE, FREE)
    directory += bytes(unused) * (-len(directory) // 128 % 4)
    directory_start = allocate(directory)
    fat_count = 1
    while math.ceil((len(sectors) + fat_count) / 128) > fat_count:
        fat_count += 1
    assert fat_count <= 109
    fat_ids = list(range(len(sectors), len(sectors) + fat_count))
    fat = links + [FAT_SECTOR] * fat_count
    fat += [FREE] * (fat_count * 128 - len(fat))
    for i in range(fat_count):
        sectors.append(struct.pack('<128I', *fat[i * 128:(i + 1) * 128]))
    header = bytearray(512)
    header[:8] = bytes.fromhex('D0CF11E0A1B11AE1')
    struct.pack_into('<HHHHH', header, 24, 0x3e, 3, 0xfffe, 9, 6)
    struct.pack_into('<IIIIIIIII', header, 40, 0, fat_count, directory_start, 0, 4096,
                     mini_fat_start, len(mini_table) // 512, END, 0)
    struct.pack_into('<109I', header, 76, *(fat_ids + [FREE] * (109 - fat_count)))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + b''.join(sectors))
    if olefile is not None:
        with olefile.OleFileIO(path) as ole:
            for name, value in streams.items():
                assert ole.openstream(name).read() == value


def point(record, prefix='LOCATION'):
    return (float(record.get(prefix + '.X', 0)), float(record.get(prefix + '.Y', 0)))


def pin_end(record):
    x, y = point(record)
    dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[int(record['PINCONGLOMERATE']) & 3]
    size = float(record.get('PINLENGTH', 0))
    return (x + dx * size, y + dy * size)


class Sheet:
    def __init__(self, size=(5400, 4200)):
        template = [{'HEADER': 'Protel for Windows - Schematic Capture Binary File Version 5.0', 'WEIGHT': '1'}, {'RECORD': '31', 'FONTIDCOUNT': '9', 'SIZE1': '9', 'FONTNAME1': 'Times New Roman', 'SIZE2': '8', 'FONTNAME2': 'Times New Roman', 'SIZE3': '12', 'FONTNAME3': 'Times New Roman', 'SIZE4': '16', 'FONTNAME4': 'Times New Roman', 'SIZE5': '11', 'FONTNAME5': 'Times New Roman', 'SIZE6': '8', 'FONTNAME6': 'Times New Roman', 'SIZE7': '12', 'FONTNAME7': 'Times New Roman', 'SIZE8': '9', 'FONTNAME8': 'Times New Roman', 'USEMBCS': 'T', 'ISBOC': 'T', 'HOTSPOTGRIDON': 'T', 'HOTSPOTGRIDSIZE': '10', 'SHEETSTYLE': '3', 'USECUSTOMSHEET': 'T', 'SYSTEMFONT': '1', 'BORDERON': 'F', 'TITLEBLOCKON': 'F', 'SHEETNUMBERSPACESIZE': '4', 'AREACOLOR': '16777215', 'SNAPGRIDON': 'T', 'SNAPGRIDSIZE': '10', 'VISIBLEGRIDON': 'T', 'VISIBLEGRIDSIZE': '10', 'CUSTOMX': '5400', 'CUSTOMY': '4200', 'CUSTOMXZONES': '6', 'CUSTOMYZONES': '5', 'CUSTOMMARGINWIDTH': '20', 'DISPLAY_UNIT': '4', 'REFERENCEZONESON': 'F', 'SIZE9': '12', 'FONTNAME9': 'SimSun'}]
        self.records = copy.deepcopy(template[:2])
        # 分区数随图幅变化，小图纸不挤满 6×5 的分区标记。
        self.records[1].update(CUSTOMX=str(size[0]), CUSTOMY=str(size[1]),
                               CUSTOMXZONES=str(min(8, max(2, round(size[0] / 100)))),
                               CUSTOMYZONES=str(min(6, max(2, round(size[1] / 100)))),
                               SIZE1='9', SIZE2='8', SIZE3='12', SIZE4='16',
                               AREACOLOR='16777215', FONTIDCOUNT='9', SIZE9='12', FONTNAME9='SimSun')
        self.pins = {}

    def add(self, kind, **values):
        row = {'RECORD': str(kind)}
        row.update({k: str(round(v) if isinstance(v, float) else v) for k, v in values.items()})
        self.records.append(row)
        return len(self.records) - 1

    def text(self, x, y, text, font=1, color=8388608, owner=None):
        kw = {'LOCATION.X': round(x, 3), 'LOCATION.Y': round(y, 3), 'COLOR': color,
              'FONTID': font, 'TEXT': text, 'OWNERPARTID': -1}
        if owner is not None:
            kw['OWNERINDEX'] = owner - 1
            kw['OWNERPARTID'] = 1
        return self.add(4, **kw)

    def wire(self, *points, width=1, color=8388608):
        assert len(points) >= 2
        for a, b in zip(points, points[1:]):
            assert a[0] == b[0] or a[1] == b[1], ('非正交导线', a, b)
        kw = {'LINEWIDTH': width, 'COLOR': color, 'LOCATIONCOUNT': len(points)}
        for i, (x, y) in enumerate(points, 1):
            kw[f'X{i}'] = round(x, 3)
            kw[f'Y{i}'] = round(y, 3)
        return self.add(27, **kw)

    def line(self, a, b, owner=None, color=128, width=1):
        kw = {'LINEWIDTH': width, 'COLOR': color, 'LOCATIONCOUNT': 2,
              'X1': a[0], 'Y1': a[1], 'X2': b[0], 'Y2': b[1]}
        if owner is not None:
            kw.update(OWNERINDEX=owner - 1, OWNERPARTID=1, OWNERPARTDISPLAYMODE=0, ISNOTACCESIBLE='T')
        return self.add(6, **kw)

    def rect(self, x1, y1, x2, y2, owner=None, fill=False, width=1):
        kw = {'LOCATION.X': x1, 'LOCATION.Y': y1, 'CORNER.X': x2, 'CORNER.Y': y2,
              'LINEWIDTH': width, 'COLOR': 128, 'OWNERPARTID': -1}
        if fill:
            kw.update(AREACOLOR=11599871, ISSOLID='T')
        if owner is not None:
            kw.update(OWNERINDEX=owner - 1, OWNERPARTID=1, OWNERPARTDISPLAYMODE=0, ISNOTACCESIBLE='T')
        return self.add(14, **kw)

    def label(self, x, y, text, orientation=0):
        return self.add(25, INDEXINSHEET=-1, OWNERPARTID=-1,
                        **{'LOCATION.X': x, 'LOCATION.Y': y, 'COLOR': 128,
                           'FONTID': 1, 'TEXT': text, 'ORIENTATION': orientation})

    def junction(self, p):
        return self.add(29, INDEXINSHEET=-1, OWNERPARTID=-1,
                        **{'LOCATION.X': p[0], 'LOCATION.Y': p[1], 'COLOR': 8388608})

    def power(self, x, y, name, ground=False):
        return self.add(17, INDEXINSHEET=-1, OWNERPARTID=-1, STYLE=4 if ground else 2,
                        SHOWNETNAME='T', **{'LOCATION.X': x, 'LOCATION.Y': y,
                        'ORIENTATION': 3 if ground else 1, 'COLOR': 128, 'TEXT': name})

    def font_size(self, font):
        return float(self.records[1].get(f'SIZE{font}', 9))

    def component(self, ref, name, body, pins, comment=None, comment_pos=None, des_pos=None,
                  pin_length=20, font=1):
        x1, y1, x2, y2 = body
        idx = self.add(1, LIBREFERENCE=name, PARTCOUNT=2, DISPLAYMODECOUNT=1,
                       OWNERPARTID=-1, **{'LOCATION.X': (x1+x2)/2,
                       'LOCATION.Y': (y1+y2)/2, 'ORIENTATION': 0, 'CURRENTPARTID': 1,
                       'LIBRARYPATH': '*', 'SOURCELIBRARYNAME': '*', 'SHEETPARTFILENAME': '*',
                       'TARGETFILENAME': '*', 'UNIQUEID': hashlib.sha256(ref.encode()).hexdigest()[:8].upper(),
                       'AREACOLOR': 11599871, 'COLOR': 128, 'PARTIDLOCKED': 'F', 'DESIGNITEMID': name})
        self.rect(*body, owner=idx, fill=True)
        self.pins[ref] = {}
        for num, pname, x, y, direction, etype in pins:
            dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
            self.add(2, OWNERINDEX=idx-1, OWNERPARTID=1, FORMALTYPE=1,
                     ELECTRICAL=etype, PINCONGLOMERATE=56+direction, PINLENGTH=pin_length,
                     **{'LOCATION.X': x, 'LOCATION.Y': y, 'NAME': pname,
                        'DESIGNATOR': num, 'SWAPIDPART': 1, 'COLOR': 0})
            self.pins[ref][str(num)] = (x + dx*pin_length, y + dy*pin_length)
        # 默认位号在器件框上方、注释在下方，避免文字压住框线或引脚名。
        height = self.font_size(font)
        des_pos = des_pos or (x1, y2 + 3)
        self.add(34, OWNERINDEX=idx-1, INDEXINSHEET=-1, OWNERPARTID=-1,
                 **{'LOCATION.X': des_pos[0], 'LOCATION.Y': des_pos[1], 'COLOR': 8388608,
                    'FONTID': font, 'TEXT': ref, 'NAME': 'Designator', 'READONLYSTATE': 1})
        pos = comment_pos or (x1, y1 - 3 - height)
        self.add(41, OWNERINDEX=idx-1, INDEXINSHEET=-1, OWNERPARTID=-1,
                 **{'LOCATION.X': pos[0], 'LOCATION.Y': pos[1], 'COLOR': 8388608,
                    'FONTID': font, 'TEXT': comment or name, 'NAME': 'Comment'})
        return idx

    def passive(self, ref, value, x, y, vertical=False, kind='R', scale=.5, grid=10, font=1,
                des_pos=None, comment_pos=None):
        """按比例绘制两脚无源件；引脚热端始终落在栅格上，文字保持完整字高。"""
        s = scale
        reach = round(20*s)
        hot = max(grid, round((20*s + 12*s) / grid) * grid)
        if hot - reach < 2:
            hot += grid
        length = hot - reach

        def at(u, v):
            # u 沿引脚轴向，v 为横向；竖放时轴向朝上。
            return (x - v, y + u) if vertical else (x + u, y + v)

        idx = self.add(1, LIBREFERENCE=kind, PARTCOUNT=2, DISPLAYMODECOUNT=1, OWNERPARTID=-1,
                       **{'LOCATION.X': x, 'LOCATION.Y': y, 'ORIENTATION': 0, 'CURRENTPARTID': 1,
                          'LIBRARYPATH': '*', 'SOURCELIBRARYNAME': '*', 'SHEETPARTFILENAME': '*',
                          'TARGETFILENAME': '*', 'UNIQUEID': hashlib.sha256(ref.encode()).hexdigest()[:8].upper(),
                          'COLOR': 128, 'DESIGNITEMID': kind})
        self.pins[ref] = {}
        # 横放时 1 脚在左、竖放时 1 脚在上，与原有计划的引脚编号保持一致。
        ends = ((1, '1', 1), (-1, '2', 3)) if vertical else ((-1, '1', 2), (1, '2', 0))
        for sign, num, direction in ends:
            px, py = at(sign*reach, 0)
            self.add(2, OWNERINDEX=idx-1, OWNERPARTID=1, FORMALTYPE=1, ELECTRICAL=4,
                     PINCONGLOMERATE=32+direction, PINLENGTH=length,
                     **{'LOCATION.X': px, 'LOCATION.Y': py, 'NAME': num, 'DESIGNATOR': num,
                        'SWAPIDPART': 1, 'COLOR': 0})
            self.pins[ref][num] = at(sign*hot, 0)
        half = 0
        if kind == 'C':
            gap, plate = max(2, round(4*s)), round(14*s)
            for u in (-gap, gap):
                self.line(at(u, -plate), at(u, plate), owner=idx)
            self.line(at(-reach, 0), at(-gap, 0), owner=idx)
            self.line(at(reach, 0), at(gap, 0), owner=idx)
            half = plate
        elif kind == 'L':
            pts = []
            for c in (-15, -5, 5, 15):
                for i in range(9):
                    a = math.pi*(1-i/8)
                    pts.append(tuple(round(v) for v in at(s*(c + 5*math.cos(a)), s*6*math.sin(a))))
            kw = {'OWNERINDEX': idx-1, 'OWNERPARTID': 1, 'OWNERPARTDISPLAYMODE': 0, 'ISNOTACCESIBLE': 'T',
                  'LINEWIDTH': 1, 'COLOR': 8388608, 'LOCATIONCOUNT': len(pts)}
            for i, (px, py) in enumerate(pts, 1):
                kw[f'X{i}'] = px
                kw[f'Y{i}'] = py
            self.add(6, **kw)
            half = round(6*s)
        elif kind == 'Y':
            box, plate = round(9*s), round(14*s)
            (ax, ay), (bx, by) = at(-box, -round(13*s)), at(box, round(13*s))
            self.rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), owner=idx)
            for u in (-plate, plate):
                self.line(at(u, -round(17*s)), at(u, round(17*s)), owner=idx)
                self.line(at(u, 0), at(reach if u > 0 else -reach, 0), owner=idx)
            half = round(17*s)
        else:
            half = max(2, round(6*s))
            (ax, ay), (bx, by) = at(-reach, -half), at(reach, half)
            self.rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), owner=idx)
        height = self.font_size(font)
        if vertical:
            des_pos = des_pos or (x + half + 3, y + 1)
            comment_pos = comment_pos or (x + half + 3, y - 1 - height)
        else:
            des_pos = des_pos or (x - reach, y + half + 2 + round(1.1*height))
            comment_pos = comment_pos or (x - reach, y + half + 1)
        for record, pos, text, name in ((34, des_pos, ref, 'Designator'), (41, comment_pos, value, 'Comment')):
            extra = {'READONLYSTATE': 1} if record == 34 else {}
            self.add(record, OWNERINDEX=idx-1, INDEXINSHEET=-1, OWNERPARTID=-1,
                     **{'LOCATION.X': pos[0], 'LOCATION.Y': pos[1], 'COLOR': 8388608, 'FONTID': font,
                        'TEXT': text, 'NAME': name}, **extra)
        return idx

    def save(self, path):
        self.records[0]['WEIGHT'] = str(len(self.records)-1)
        header = b''.join(encode(d) for d in self.records)
        write_compound(path, {'FileHeader':header,
                            'Storage':encode({'HEADER':'Icon storage'}),
                            'Additional':encode({'HEADER':'Protel for Windows - Schematic Capture Binary File Version 5.0'})})
        if olefile is not None:
            reopened = read(path)
            assert reopened == self.records
        return Path(path)
