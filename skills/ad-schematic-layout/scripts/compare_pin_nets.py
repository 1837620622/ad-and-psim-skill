"""按物理引脚的同网伙伴比较拓扑，不依赖自动生成网名。"""

import argparse
import csv
import json
from pathlib import Path
import sys


def read_text(path):
    raw = Path(path).read_bytes()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16')
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'无法识别编码：{path}')


def load_pin_map(path):
    content = read_text(path)
    pins = {}

    def add(pin, net):
        pin, net = str(pin).strip(), str(net).strip()
        if not pin or not net:
            raise ValueError('物理引脚和网络名不能是空值')
        if pin in pins:
            raise ValueError(f'物理引脚重复归属：{pin}')
        pins[pin] = net

    if content.lstrip().startswith('{'):

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('JSON 重复字段：' + key)
                result[key] = value
            return result

        data = json.loads(content, object_pairs_hook=unique_pairs)
        if not isinstance(data, dict) or not isinstance(data.get('pin_map'), dict):
            raise ValueError('JSON 须含 pin_map 对象：物理引脚 -> 网络名')
        for pin, net in data['pin_map'].items():
            if not isinstance(net, str):
                raise ValueError(f'网络名须为字符串：{pin}')
            add(pin, net)
    else:
        for number, fields in enumerate(csv.reader(content.splitlines(), delimiter='|'), 1):
            if not fields or all(not f.strip() for f in fields):
                continue
            if len(fields) != 3:
                raise ValueError(f'第 {number} 行须为 网络名|物理位号|引脚号')
            net, ref, pin = (f.strip() for f in fields)
            if not ref or not pin:
                raise ValueError(f'第 {number} 行的位号或引脚为空')
            add(ref + '.' + pin, net)
    if not pins:
        raise ValueError('网表没有物理引脚')
    return pins


def peers(pin_map):
    nets = {}
    for pin, net in pin_map.items():
        nets.setdefault(net, set()).add(pin)
    frozen = {net: frozenset(members) for net, members in nets.items()}
    return {pin: frozen[net] for pin, net in pin_map.items()}


def compare(expected, actual):
    left, right = peers(expected), peers(actual)
    missing, added = sorted(left.keys() - right.keys()), sorted(right.keys() - left.keys())
    changed = []
    for pin in sorted(left.keys() & right.keys()):
        if left[pin] != right[pin]:
            changed.append(
                {
                    'pin': pin,
                    'expected_only_members': sorted(left[pin] - right[pin]),
                    'actual_only_members': sorted(right[pin] - left[pin]),
                }
            )
    return {
        'match': not (missing or added or changed),
        'expected_pin_count': len(left),
        'actual_pin_count': len(right),
        'missing_pins': missing,
        'added_pins': added,
        'changed_pins': changed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected', type=Path)
    parser.add_argument('actual', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.output and args.output.resolve() in (args.expected.resolve(), args.actual.resolve()):
            raise ValueError('输出路径不能覆盖输入')
        result = compare(load_pin_map(args.expected), load_pin_map(args.actual))
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + '\n', encoding='utf-8')
        print(text)
        return 0 if result['match'] else 1
    except (ValueError, OSError, UnicodeError, csv.Error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
