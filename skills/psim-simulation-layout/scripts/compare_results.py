"""跨系统比较文件和波形，明确区分字节相同、数值相等和容差内相符。"""

import argparse
from contextlib import contextmanager
import csv
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
import re
import sys

# 定位数科学计数法（PSIM、SIMVIEW 文本导出的写法，如 1.2345678E-005）；尾数位数相同才算定位数。
FIXED = re.compile(r'\s*[+-]?\d\.(\d+)[eEdD][+-]?\d+\s*')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            result.update(chunk)
    return result.hexdigest()


def compare_files(reference, candidate):
    reference, candidate = Path(reference).resolve(), Path(candidate).resolve()
    left, right = digest(reference), digest(candidate)
    return {
        'passed': left == right,
        'equivalence': 'byte_identical' if left == right else 'different',
        'reference': str(reference),
        'candidate': str(candidate),
        'reference_sha256': left,
        'candidate_sha256': right,
    }


def _dialect(path):
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            with Path(path).open(encoding=encoding) as probe:
                sample = probe.read(8192)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('CSV 编码无法识别')
    try:
        return encoding, csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        return encoding, csv.excel


def printed_digits(path):
    """CSV 的全部数字都按同一尾数位数的科学计数法写出时，返回尾数小数位数；否则（如最短往返写法）返回 None。"""
    encoding, dialect = _dialect(path)
    digits = None
    with Path(path).open(encoding=encoding, newline='') as stream:
        reader = csv.reader(stream, dialect)
        next(reader, None)
        for row in reader:
            for cell in row:
                if not cell.strip():
                    continue
                match = FIXED.fullmatch(cell)
                if match is None or digits not in (None, len(match[1])):
                    return None
                digits = len(match[1])
    return digits


@contextmanager
def table(path):
    encoding, dialect = _dialect(path)
    with Path(path).open(encoding=encoding, newline='') as stream:
        reader = csv.reader(stream, dialect)
        header = next(reader, [])
        header = [name.strip() for name in header]
        if not header or not all(header) or len(set(header)) != len(header):
            raise ValueError('CSV 列名为空或重复')

        def rows():
            for number, row in enumerate(reader, 2):
                if not row or all(not cell.strip() for cell in row):
                    continue
                if len(row) != len(header):
                    raise ValueError(f'CSV 第 {number} 行字段数量不一致')
                values = [float(v.strip().replace('D', 'E').replace('d', 'e')) for v in row]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError(f'CSV 第 {number} 行含非有限值')
                yield dict(zip(header, values))

        yield header, rows()


def compare_waveforms(reference, candidate, *, signals=None, time='Time', atol=0.0, rtol=0.0, time_atol=0.0):
    if any(not math.isfinite(v) or v < 0 for v in (atol, rtol, time_atol)):
        raise ValueError('容差须为有限非负数')
    result = compare_files(reference, candidate)
    digits = printed_digits(reference)

    def printed(left, right):
        """参考只写到有限位数时：候选值按同样的位数写出后与参考相同。"""
        return digits is not None and float(f'{right:.{digits}e}') == left

    with table(reference) as (left_header, left_rows), table(candidate) as (right_header, right_rows):
        if time not in left_header or time not in right_header:
            raise ValueError('两个 CSV 都须有时间列')
        columns = list(dict.fromkeys(signals)) if signals else [n for n in left_header if n != time]
        if not columns or time in columns:
            raise ValueError('至少指定一个非时间信号')
        if not signals and set(left_header) != set(right_header):
            raise ValueError('完整比较要求两份 CSV 的列集合一致')
        if any(name not in left_header or name not in right_header for name in columns):
            raise ValueError('待比较的信号列缺失')
        stats = {name: {'max_absolute_error': 0.0, 'mismatched_samples': 0} for name in columns}
        mismatch, count, previous_left, previous_right = [], 0, None, None
        equal, same_digits, complete = True, True, True
        max_time_error = 0.0
        for left, right in zip_longest(left_rows, right_rows):
            if left is None or right is None:
                complete = False
                break
            count += 1
            t1, t2 = left[time], right[time]
            if previous_left is not None and (t1 <= previous_left or t2 <= previous_right):
                raise ValueError('CSV 时间必须严格递增')
            previous_left, previous_right = t1, t2
            dt = abs(t1 - t2)
            max_time_error = max(max_time_error, dt)
            equal = equal and dt == 0
            same_digits = same_digits and (dt == 0 or printed(t1, t2))
            if dt > time_atol and not printed(t1, t2):
                complete = False
                if len(mismatch) < 10:
                    mismatch.append({'sample': count, 'signal': time, 'reference': t1, 'candidate': t2})
            for name in columns:
                error = abs(left[name] - right[name])
                equal = equal and error == 0
                same = error == 0 or printed(left[name], right[name])
                same_digits = same_digits and same
                stats[name]['max_absolute_error'] = max(stats[name]['max_absolute_error'], error)
                if error > atol + rtol * abs(left[name]) and not same:
                    stats[name]['mismatched_samples'] += 1
                    if len(mismatch) < 10:
                        mismatch.append(
                            {'sample': count, 'signal': name, 'reference': left[name], 'candidate': right[name]}
                        )
        if count < 2:
            raise ValueError('波形比较至少需要两个样本')
    passed = complete and all(not item['mismatched_samples'] for item in stats.values())
    if not passed:
        equivalence = 'different'
    elif result['passed'] or equal:
        equivalence = 'byte_identical' if result['passed'] else 'numeric_equal'
    else:
        equivalence = 'printed_digits_equal' if same_digits else 'within_tolerance'
    result.update(
        passed=passed,
        equivalence=equivalence,
        reference_significant_digits=None if digits is None else digits + 1,
        samples_compared=count,
        complete_column_set=not bool(signals),
        tolerances={'absolute': atol, 'relative': rtol, 'time_absolute_s': time_atol},
        max_time_error_s=max_time_error,
        signals=stats,
        first_mismatches=mismatch,
        limitations='只比较给定文件和信号；不运行求解器，不证明未提供工况相同；不插值、不平滑、不修改原始数据。',
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--waveforms', action='store_true')
    parser.add_argument('--signal', action='append')
    parser.add_argument('--time', default='Time')
    parser.add_argument('--atol', type=float, default=0.0)
    parser.add_argument('--rtol', type=float, default=0.0)
    parser.add_argument('--time-atol', type=float, default=0.0)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.resolve() in (args.reference.resolve(), args.candidate.resolve()):
            raise ValueError('报告不能覆盖输入文件')
        result = (
            compare_waveforms(
                args.reference,
                args.candidate,
                signals=args.signal,
                time=args.time,
                atol=args.atol,
                rtol=args.rtol,
                time_atol=args.time_atol,
            )
            if args.waveforms
            else compare_files(args.reference, args.candidate)
        )
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + '\n', encoding='utf-8')
        print(text)
        return 0 if result['passed'] else 1
    except (ValueError, OSError, UnicodeError, csv.Error) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
