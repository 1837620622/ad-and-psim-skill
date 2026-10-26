"""为测试构造最小 EMF；只包含审查工具读取的记录。"""
import struct


def record(kind, payload):
    payload = payload + b'\x00' * (-len(payload) % 4)
    return struct.pack('<II', kind, 8 + len(payload)) + payload


def text(value, box, reference=None):
    reference = reference or box[:2]
    encoded = value.encode('utf-16le')
    offset = 76
    body = struct.pack('<4iIff', *box, 1, 1., 1.)
    body += struct.pack('<2iIII4iI', *reference, len(value), offset, 0, *box, 0)
    body += encoded
    return record(84, body)


def polyline16(points, bounds=None):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    bounds = bounds or (min(xs), min(ys), max(xs), max(ys))
    body = struct.pack('<4iI', *bounds, len(points)) + b''.join(struct.pack('<2h', *p) for p in points)
    return record(87, body)


def ellipse(box):
    return record(42, struct.pack('<4i', *box))


def set_map_mode(mode):
    return record(17, struct.pack('<I', mode))


def set_extent(kind, x, y):
    return record(kind, struct.pack('<2i', x, y))


def emf(*records, bounds=(0, 0, 1000, 1000)):
    body = b''.join(records) + record(14, struct.pack('<III', 0, 16, 20))
    header = struct.pack('<II4i4i', 1, 88, *bounds, 0, 0, 26458, 26458)
    header += b' EMF' + struct.pack('<IIIHHIII', 0x10000, 88 + len(body), len(records) + 2, 1, 0, 0, 0, 0)
    header += struct.pack('<2i2i', 1000, 1000, 264, 264)
    assert len(header) == 88
    return header + body
