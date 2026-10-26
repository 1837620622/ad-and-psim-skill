"""筛查原生 EMF 文字字框；不代替压线、符号和电气检查。"""
import argparse
import json
import struct
from pathlib import Path
import sys


def parse_emf(raw):
    if len(raw) < 88 or struct.unpack_from('<I', raw)[0] != 1 or raw[40:44] != b' EMF':
        raise ValueError('不是有效的 EMF 文件头')
    bounds = struct.unpack_from('<4i', raw, 8)
    offset, texts, unsupported, invalid = 0, [], {}, 0
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError('EMF 记录头截断')
        kind, size = struct.unpack_from('<II', raw, offset)
        if size < 8 or size % 4 or offset + size > len(raw):
            raise ValueError(f'EMF 记录大小无效，偏移 {offset}')
        if kind == 84:
            if size < 76:
                raise ValueError('Unicode 文字记录截断')
            count, at = struct.unpack_from('<II', raw, offset + 44)
            if count and (at < 76 or at + count * 2 > size):
                raise ValueError('Unicode 文字超出所属记录')
            text = raw[offset + at:offset + at + count * 2].decode('utf-16le')
            box = struct.unpack_from('<4i', raw, offset + 8)
            if text.strip():
                if box[2] <= box[0] or box[3] <= box[1]:
                    invalid += 1
                else:
                    texts.append({'text': text, 'box': list(box)})
        elif kind in (83, 96, 97, 108):
            unsupported[str(kind)] = unsupported.get(str(kind), 0) + 1
        offset += size
    return bounds, texts, unsupported, invalid


def review(raw, border=None, overlap_ratio=.2):
    bounds, texts, unsupported, invalid = parse_emf(raw)
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
                overlaps.append({'first': i, 'second': j, 'fraction_of_smaller_box': ratio,
                                 'texts': [a['text'], texts[j]['text']]})
    outside = [i for i, a in enumerate(texts)
               if a['box'][0] < border[0] or a['box'][1] < border[1]
               or a['box'][2] > border[2] or a['box'][3] > border[3]]
    return {'text_count': len(texts), 'border': list(border), 'overlaps': overlaps,
            'outside_indices': outside, 'texts': texts,
            'unsupported_text_record_counts': unsupported, 'invalid_text_bounds': invalid,
            'coverage_complete_for_text_records': not (unsupported or invalid),
            'limitations': '仅筛查受支持文字字框；不检查压线、符号遮挡、实际字形、视觉质量或电气连接。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('emf', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--border', help='EMF 设备坐标 xmin,ymin,xmax,ymax')
    parser.add_argument('--overlap-ratio', type=float, default=.2)
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
        return int(bool(result['overlaps'] or result['outside_indices'] or
                        not result['coverage_complete_for_text_records']))
    except (ValueError, OSError, UnicodeError, struct.error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
