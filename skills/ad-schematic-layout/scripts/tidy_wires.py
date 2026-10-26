"""整理导线：合并共线重叠的线段，在分支点和引脚热端处分段，只在 T 形分支放连接点。"""

from collections import defaultdict
from copy import deepcopy

# 引脚从热端指向器件本体的方向（按 PINCONGLOMERATE 低两位）。
PIN_SIDE = ('L', 'D', 'R', 'U')


def _pin_hot_ends(records):
    pins = defaultdict(set)
    for row in records:
        if row.get('RECORD') != '2':
            continue
        direction = int(row['PINCONGLOMERATE']) & 3
        dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
        length = float(row.get('PINLENGTH', 0))
        hot = (round(float(row['LOCATION.X']) + dx * length), round(float(row['LOCATION.Y']) + dy * length))
        pins[hot].add(PIN_SIDE[direction])
    return pins


def _directions(point, segments):
    px, py = point
    found = set()
    for a, b in segments:
        if a[1] == b[1] == py and min(a[0], b[0]) <= px <= max(a[0], b[0]):
            if min(a[0], b[0]) < px:
                found.add('L')
            if max(a[0], b[0]) > px:
                found.add('R')
        elif a[0] == b[0] == px and min(a[1], b[1]) <= py <= max(a[1], b[1]):
            if min(a[1], b[1]) < py:
                found.add('D')
            if max(a[1], b[1]) > py:
                found.add('U')
    return found


def tidy(records):
    groups = defaultdict(list)
    segments, vertices, junctions = [], set(), set()
    pins = _pin_hot_ends(records)
    for row in records:
        if row.get('RECORD') == '29':
            junctions.add((int(row['LOCATION.X']), int(row['LOCATION.Y'])))
        if row.get('RECORD') != '27':
            continue
        points = [(int(row[f'X{i}']), int(row[f'Y{i}'])) for i in range(1, int(row['LOCATIONCOUNT']) + 1)]
        vertices.update(points)
        style = (row.get('LINEWIDTH', '1'), row.get('COLOR', '8388608'))
        for a, b in zip(points, points[1:]):
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f'非正交导线：{a} -> {b}')
            segments.append((a, b))
            if a[1] == b[1]:
                groups[('H', a[1], *style)].append(sorted((a[0], b[0])))
            else:
                groups[('V', a[0], *style)].append(sorted((a[1], b[1])))

    branch_points, pin_cuts = set(), set()
    for point in vertices | junctions | set(pins):
        found = _directions(point, segments)
        if point in pins and found:
            # 导线在热端处保持端点，AD 直接按端点连接。
            pin_cuts.add(point)
            found |= pins[point]
        if len(found) >= 3:
            branch_points.add(point)

    kept = [i for i, row in enumerate(records) if row.get('RECORD') not in ('27', '29')]
    mapping = {old: new for new, old in enumerate(kept)}
    result = []
    for i in kept:
        row = deepcopy(records[i])
        if 'OWNERINDEX' in row:
            owner = int(row['OWNERINDEX']) + 1
            if owner in mapping:
                row['OWNERINDEX'] = str(mapping[owner] - 1)
        result.append(row)

    cut_points = branch_points | pin_cuts
    for (axis, position, width, color), intervals in sorted(groups.items()):
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            along = {
                (x if axis == 'H' else y)
                for x, y in cut_points
                if (y if axis == 'H' else x) == position and start < (x if axis == 'H' else y) < end
            }
            cuts = sorted({start, end} | along)
            for lo, hi in zip(cuts, cuts[1:]):
                a, b = ((lo, position), (hi, position)) if axis == 'H' else ((position, lo), (position, hi))
                result.append(
                    {
                        'RECORD': '27',
                        'LINEWIDTH': width,
                        'COLOR': color,
                        'LOCATIONCOUNT': '2',
                        'X1': str(a[0]),
                        'Y1': str(a[1]),
                        'X2': str(b[0]),
                        'Y2': str(b[1]),
                    }
                )
    for x, y in sorted(branch_points):
        result.append(
            {
                'RECORD': '29',
                'INDEXINSHEET': '-1',
                'OWNERPARTID': '-1',
                'LOCATION.X': str(x),
                'LOCATION.Y': str(y),
                'COLOR': '8388608',
            }
        )
    return result
