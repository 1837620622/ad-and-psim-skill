"""测量原生导出的 CSV；时间加权统计不等于自动确认稳态或内部求解步长。"""
import argparse
from array import array
from bisect import bisect_left, bisect_right
import csv
import json
import math
from pathlib import Path
import statistics
import sys


def load_csv(path, names, time_name='Time', encoding=None):
    path = Path(path)
    if encoding is None:
        for candidate in ('utf-8-sig', 'gb18030'):
            try:
                with path.open(encoding=candidate, newline='') as stream:
                    stream.read(8192)
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
    if encoding is None:
        raise ValueError('无法识别 CSV 编码，请指定 --encoding')
    requested = list(dict.fromkeys([time_name] + list(names)))
    result = {name: array('d') for name in requested}
    with path.open(encoding=encoding, newline='') as stream:
        sample = stream.read(8192)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(stream, dialect)
        header = next(reader, None)
        if not header:
            raise ValueError('CSV 没有表头')
        header = [h.strip() for h in header]
        if len(set(header)) != len(header):
            raise ValueError('CSV 列名重复')
        missing = set(requested) - set(header)
        if missing:
            raise ValueError('缺少列：' + ', '.join(sorted(missing)))
        indices = {name: header.index(name) for name in requested}
        for number, row in enumerate(reader, 2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise ValueError(f'第 {number} 行字段数量与表头不符')
            for name, index in indices.items():
                try:
                    value = float(row[index].strip().replace('D', 'E').replace('d', 'e'))
                except ValueError as error:
                    raise ValueError(f'第 {number} 行 {name} 不是 SI 数值') from error
                if not math.isfinite(value):
                    raise ValueError(f'第 {number} 行 {name} 不是有限值')
                result[name].append(value)
    times = result.pop(time_name)
    if len(times) < 2 or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('时间至少两个点且须严格递增，不能重复或倒退')
    return times, result, encoding


def interpolate(times, values, t):
    pos = bisect_left(times, t)
    if pos < len(times) and times[pos] == t:
        return values[pos]
    if pos == 0 or pos == len(times):
        raise ValueError('窗口超出已有数据，不做外推')
    fraction = (t - times[pos - 1]) / (times[pos] - times[pos - 1])
    return values[pos - 1] + fraction * (values[pos] - values[pos - 1])


def clip(times, data, start, end):
    if not (math.isfinite(start) and math.isfinite(end) and times[0] <= start < end <= times[-1]):
        raise ValueError('分析窗口须在原始时间范围内，且 start < end')
    lo, hi = bisect_right(times, start), bisect_left(times, end)
    new_times = array('d', [start])
    new_times.extend(times[lo:hi])
    new_times.append(end)
    new_data = {}
    for name, values in data.items():
        series = array('d', [interpolate(times, values, start)])
        series.extend(values[lo:hi])
        series.append(interpolate(times, values, end))
        new_data[name] = series
    return new_times, new_data


def moments(times, values):
    duration = times[-1] - times[0]
    integral = math.fsum((b - a) * (x + y) / 2
                         for a, b, x, y in zip(times, times[1:], values, values[1:]))
    square = math.fsum((b - a) * (x*x + x*y + y*y) / 3
                       for a, b, x, y in zip(times, times[1:], values, values[1:]))
    low, high = min(values), max(values)
    return {'mean': integral / duration, 'rms': math.sqrt(max(0., square / duration)),
            'min': low, 'max': high, 'peak_to_peak': high - low}


def mean_product(times, left, right):
    # 两条线性插值曲线的乘积为二次式，按段积分而非均值相乘。
    integral = math.fsum((b - a) * (2*x0*y0 + x0*y1 + x1*y0 + 2*x1*y1) / 6
                         for a, b, x0, x1, y0, y1 in
                         zip(times, times[1:], left, left[1:], right, right[1:]))
    return integral / (times[-1] - times[0])


def gate_frequency(times, values, threshold):
    edges = []
    for t0, t1, y0, y1 in zip(times, times[1:], values, values[1:]):
        if y0 < threshold <= y1:
            edges.append(t0 + (threshold - y0) * (t1 - t0) / (y1 - y0))
    if len(edges) < 3:
        return {'status': 'insufficient_rising_edges', 'edge_count': len(edges)}
    periods = [b - a for a, b in zip(edges, edges[1:])]
    return {'status': 'measured', 'edge_count': len(edges),
            'average_hz': (len(edges) - 1) / (edges[-1] - edges[0]),
            'median_period_hz': 1 / statistics.median(periods),
            'min_cycle_hz': 1 / max(periods), 'max_cycle_hz': 1 / min(periods),
            'method': '原始输出点之间线性插值的阈值上升沿；不能恢复采样漏掉的脉冲。'}


def measure(times, data, *, pin=None, pout=None, vin=None, iin=None, vout=None, iout=None,
            start=None, end=None, fundamental=None, cycles=None, steady=False,
            gate=None, threshold=.5, capacitors=(), inductors=(), ac_input=False):
    if any(not math.isfinite(t) for t in times) or len(times) < 2 or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('时间须为严格递增的有限序列')
    if any(len(values) != len(times) or any(not math.isfinite(v) for v in values) for values in data.values()):
        raise ValueError('信号长度或有限值检查失败')
    powers = bool(pin or pout)
    if powers:
        if not (pin and pout) or any((vin, iin, vout, iout)):
            raise ValueError('使用完整 pin/pout，或完整 vin/iin/vout/iout，不能混用')
    elif not all((vin, iin, vout, iout)):
        raise ValueError('V/I 模式须同时提供 vin、iin、vout、iout')
    if fundamental is not None and (not math.isfinite(fundamental) or fundamental <= 0):
        raise ValueError('fundamental-hz 须为有限正数')
    finish = times[-1] if end is None else end
    if cycles is not None:
        if not isinstance(cycles, int) or cycles <= 0 or fundamental is None or start is not None:
            raise ValueError('cycles 须为正整数并指定 fundamental-hz，且不能同时指定 start')
        begin = finish - cycles / fundamental
    else:
        begin = times[0] if start is None else start
    # 仅修正浮点计算的边界舍入误差，不允许实际外推。
    tolerance = max(1e-15, abs(times[-1] - times[0]) * 1e-12)
    if times[0] - tolerance <= begin < times[0]:
        begin = times[0]
    if times[-1] < finish <= times[-1] + tolerance:
        finish = times[-1]
    t, values = clip(times, data, begin, finish)
    stats = {name: moments(t, series) for name, series in values.items()}
    try:
        p_in = stats[pin]['mean'] if powers else mean_product(t, values[vin], values[iin])
        p_out = stats[pout]['mean'] if powers else mean_product(t, values[vout], values[iout])
    except KeyError as error:
        raise ValueError(f'缺少功率计算信号：{error.args[0]}') from error
    duration = finish - begin
    intervals = [b - a for a, b in zip(times, times[1:])]
    sample = {'min_s': min(intervals), 'max_s': max(intervals), 'median_s': statistics.median(intervals),
              'meaning': '原始输出采样间隔；不是经独立验证的内部求解步长。'}
    ratio = 100 * p_out / p_in if p_in > 0 else None
    storage = []
    for kind, terms in (('capacitor', capacitors), ('inductor', inductors)):
        for name, coefficient in terms:
            if coefficient <= 0 or not math.isfinite(coefficient):
                raise ValueError('储能参数须为有限正数，且与信号使用同一参照侧')
            if name not in values:
                raise ValueError(f'缺少储能信号：{name}')
            v = values[name]
            storage.append({'kind': kind, 'signal': name, 'coefficient_si': coefficient,
                            'energy_change_J': .5 * coefficient * (v[-1]**2 - v[0]**2)})
    known_energy = math.fsum(term['energy_change_J'] for term in storage)
    result = {'window_s': [begin, finish], 'duration_s': duration, 'sample_count_in_window': len(t),
              'output_sampling_interval': sample, 'signals': stats, 'input_power_W': p_in,
              'output_power_W': p_out, 'power_ratio_percent': ratio,
              'steady_state_asserted_by_caller': bool(steady),
              'efficiency_percent': ratio if steady and ratio is not None else None,
              'known_storage_terms': storage,
              'known_storage_power_W': known_energy / duration if storage else None,
              'residual_after_known_storage_W': p_in - p_out - known_energy / duration if storage else None,
              'limitations': '需核对稳态、参照侧、测量方向、模型损耗与采样收敛；没有自动进行工程验收。'}
    if ratio is not None and ratio > 100:
        result['power_ratio_above_100_percent'] = True
    if p_in <= 0:
        result['forward_efficiency_status'] = 'non_positive_input_power'
    if not powers:
        apparent = stats[vin]['rms'] * stats[iin]['rms']
        result['input_power_over_rms_product'] = p_in / apparent if apparent > 0 else None
        if ac_input:
            if fundamental is None:raise ValueError('AC 功率因数须指定 fundamental-hz 并核对整周期窗口')
            count=duration*fundamental
            if not math.isclose(count,round(count),rel_tol=0,abs_tol=1e-7):raise ValueError('AC 功率因数须使用完整工频周期')
            result['input_total_power_factor'] = p_in / apparent if apparent > 0 else None
    elif ac_input:raise ValueError('AC 功率因数需要 V/I 模式')
    if gate:
        if not math.isfinite(threshold) or gate not in values:
            raise ValueError('门极信号与有限阈值必须有效')
        result['gate_frequency'] = gate_frequency(t, values[gate], threshold)
    if fundamental is not None and duration + tolerance >= 2 / fundamental:
        period = 1 / fundamental
        first=finish-2*period
        if times[0]-tolerance<=first<times[0]:first=times[0]
        t1, d1 = clip(times, data, first, finish - period)
        t2, d2 = clip(times, data, finish - period, finish)
        result['last_two_periods'] = {}
        for name in data:
            a, b = moments(t1, d1[name]), moments(t2, d2[name])
            scale = max(a['rms'], b['rms'], 1e-15)
            result['last_two_periods'][name] = {
                'previous_mean': a['mean'], 'last_mean': b['mean'],
                'mean_change_over_rms_scale': (b['mean'] - a['mean']) / scale,
                'rms_relative_change': (b['rms'] - a['rms']) / scale}
    return result


def storage_term(text):
    try:
        name, value = text.rsplit('=', 1)
        value = float(value)
        if not name or not math.isfinite(value) or value <= 0:
            raise ValueError()
        return name, value
    except ValueError as error:
        raise argparse.ArgumentTypeError('储能项须为 列名=有限正数，使用 SI 单位') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--time', default='Time')
    parser.add_argument('--encoding')
    for name in ('pin', 'pout', 'vin', 'iin', 'vout', 'iout', 'gate'):
        parser.add_argument('--' + name)
    parser.add_argument('--signal', action='append', default=[])
    parser.add_argument('--start', type=float)
    parser.add_argument('--end', type=float)
    parser.add_argument('--fundamental-hz', type=float)
    parser.add_argument('--cycles', type=int)
    parser.add_argument('--threshold', type=float, default=.5)
    parser.add_argument('--steady', action='store_true')
    parser.add_argument('--ac-input', action='store_true',help='已确认交流输入；仅在 V/I 整周期窗口计算功率因数')
    parser.add_argument('--capacitor', action='append', type=storage_term, default=[])
    parser.add_argument('--inductor', action='append', type=storage_term, default=[])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.output and args.output.resolve() == args.csv.resolve():
            raise ValueError('输出路径不能覆盖原始 CSV')
        names = args.signal + [getattr(args, key) for key in ('pin', 'pout', 'vin', 'iin', 'vout', 'iout', 'gate')
                               if getattr(args, key)]
        names += [term[0] for term in args.capacitor + args.inductor]
        times, data, encoding = load_csv(args.csv, names, args.time, args.encoding)
        result = measure(times, data, pin=args.pin, pout=args.pout, vin=args.vin, iin=args.iin,
                         vout=args.vout, iout=args.iout, start=args.start, end=args.end,
                         fundamental=args.fundamental_hz, cycles=args.cycles, steady=args.steady,
                         gate=args.gate, threshold=args.threshold,
                         capacitors=args.capacitor, inductors=args.inductor,ac_input=args.ac_input)
        result['source'] = str(args.csv.resolve())
        result['encoding'] = encoding
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            args.output.write_text(text + '\n', encoding='utf-8')
        print(text)
        return 0
    except (ValueError, KeyError, OSError, UnicodeError, csv.Error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
