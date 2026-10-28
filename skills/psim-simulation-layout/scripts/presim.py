"""离线预仿真：不装 PSIM，在任何系统上按 PSIM 的算法（节点分析 + 固定步长梯形积分）先算一遍线性电路。

支持 R、L、C、直流源 VDC、正弦源 VSIN、电压探头 VP、地和仿真控制；元件带 CurrentFlag=1 时另输出电流列
I(名称)，方向从第一个端口流向第二个端口。遇到开关、二极管、控制电路等其他元件直接拒绝，不做近似替代。
结果标记为 portable_presim，用来在上 Windows 之前确认参数、拓扑和波形量级；交付的仿真结果仍须来自 PSIM。
"""

import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys

from psim_plan import SYMBOLS, kind, on_segment, ports, wire_points

SUFFIX = {'G': 1e9, 'M': 1e6, 'k': 1e3, 'K': 1e3, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15}
SUPPORTED = {'R', 'L', 'C', 'VDC', 'VSIN', 'VP', 'GROUND', 'SIMCONTROL', 'WIRE', 'TEXT', 'TEXTLINK'}
ALIASES = {
    'amplitude': ('Amplitude', 'Peak Amplitude', 'Vpeak'),
    'frequency': ('Frequency', 'Freq'),
    'phase': ('Phase Angle', 'Phase', 'PhaseAngle'),
    'offset': ('DC Offset', 'DCOffset', 'Offset'),
    'start': ('Tstart', 'T start', 'StartTime'),
}


def value(text, name='参数'):
    """解析 PSIM 写法的数值：1u、100m、4.7k、2M（M 为兆，m 为毫）、1e-6。"""
    if isinstance(text, (int, float)):
        return float(text)
    match = re.fullmatch(r'\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([GMkKmunpf]?)\s*', str(text))
    if not match:
        raise ValueError(f'{name} 的数值无法解析：{text!r}')
    return float(match.group(1)) * SUFFIX.get(match.group(2), 1.0)


def pick(attrs, key, default=None):
    for alias in ALIASES[key]:
        if alias in attrs:
            return value(attrs[alias], alias)
    return default


def nets(plan):
    """端口坐标 → 网络编号；地为 0。导线端点落在其他导线中段时同样相连。"""
    parent = {}

    def find(p):
        parent.setdefault(p, p)
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(a, b):
        parent[find(a)] = find(b)

    wires, grounds = [], []
    for element in plan['elements']:
        if kind(element) == 'WIRE':
            a, b = wire_points(element)
            wires.append((a, b))
            union(a, b)
        for p in ports(element):
            find(p)
            if kind(element) == 'GROUND':
                grounds.append(p)
    if not grounds:
        raise ValueError('电路没有地（Ground），无法确定参考点')
    points = list(parent)
    for segment in wires:
        for p in points:
            if on_segment(p, segment):
                union(segment[0], p)
    for p in grounds[1:]:
        union(grounds[0], p)
    ground = find(grounds[0])
    numbers = {ground: 0}
    for p in points:
        numbers.setdefault(find(p), len(numbers))
    return {p: numbers[find(p)] for p in points}, len(numbers)


def lu(matrix):
    """带部分主元的 LU 分解（原地）；奇异时报出悬空节点。"""
    n = len(matrix)
    order = list(range(n))
    for k in range(n):
        pivot = max(range(k, n), key=lambda i: abs(matrix[i][k]))
        if abs(matrix[pivot][k]) < 1e-15:
            raise ValueError('电路矩阵奇异：有悬空节点、电压源回路或只接了电容的节点')
        matrix[k], matrix[pivot] = matrix[pivot], matrix[k]
        order[k], order[pivot] = order[pivot], order[k]
        for i in range(k + 1, n):
            matrix[i][k] /= matrix[k][k]
            factor = matrix[i][k]
            if factor:
                row, top = matrix[i], matrix[k]
                for j in range(k + 1, n):
                    row[j] -= factor * top[j]
    return matrix, order


def solve(factored, rhs):
    matrix, order = factored
    n = len(matrix)
    y = [rhs[i] for i in order]
    for i in range(n):
        y[i] -= sum(matrix[i][j] * y[j] for j in range(i))
    for i in reversed(range(n)):
        y[i] = (y[i] - sum(matrix[i][j] * y[j] for j in range(i + 1, n))) / matrix[i][i]
    return y


class Circuit:
    def __init__(self, plan):
        unsupported = sorted({kind(e) for e in plan['elements']} - SUPPORTED)
        if unsupported:
            raise ValueError(
                '离线预仿真只支持线性元件 R、L、C、VDC、VSIN、VP；以下元件须在 Windows 上用 PSIM 求解：'
                + '、'.join(unsupported)
            )
        controls = [e for e in plan['elements'] if kind(e) == 'SIMCONTROL']
        if len(controls) != 1:
            raise ValueError('需要且只能有一个仿真控制（SIMCONTROL）')
        attrs = controls[0].get('attributes', {})
        missing = [key for key in ('TIMESTEP', 'TOTALTIME') if key not in attrs]
        if missing:
            raise ValueError('仿真控制缺少 ' + '、'.join(missing))
        self.step = value(attrs['TIMESTEP'], 'TIMESTEP')
        self.total = value(attrs['TOTALTIME'], 'TOTALTIME')
        self.print_time = value(attrs.get('PRINTTIME', 0), 'PRINTTIME')
        self.print_step = max(1, round(value(attrs.get('PRINTSTEP', 1), 'PRINTSTEP')))
        if not (self.step > 0 and self.total > self.step):
            raise ValueError('TIMESTEP 须为正，TOTALTIME 须大于 TIMESTEP')
        self.node, count = nets(plan)
        self.uncalibrated = sorted(
            {e.get('name') or kind(e) for e in plan['elements'] if SYMBOLS.get(kind(e), {}).get('calibrated') is False}
        )
        self.passives, self.sources, self.probes, self.currents = [], [], [], []
        for e in plan['elements']:
            t, a, name = kind(e), e.get('attributes', {}), e.get('name', '')
            if t in ('R', 'L', 'C'):
                field = {'R': 'Resistance', 'L': 'Inductance', 'C': 'Capacitance'}[t]
                if field not in a:
                    raise ValueError(f'{name} 缺少 {field}')
                amount = value(a[field], f'{name}.{field}')
                if amount <= 0:
                    raise ValueError(f'{name}.{field} 须为正数')
                p, q = (self.node[x] for x in ports(e))
                self.passives.append({'type': t, 'name': name, 'nodes': (p, q), 'value': amount})
                if str(a.get('CurrentFlag', 0)) == '1':
                    self.currents.append(('passive', len(self.passives) - 1, name))
            elif t in ('VDC', 'VSIN'):
                p, q = (self.node[x] for x in ports(e))
                if t == 'VDC':
                    level = value(a.get('Amplitude', 0), f'{name}.Amplitude')
                    source = {'kind': 'dc', 'level': level}
                else:
                    source = {
                        'kind': 'sin',
                        'peak': pick(a, 'amplitude', 0.0),
                        'frequency': pick(a, 'frequency', 0.0),
                        'phase': math.radians(pick(a, 'phase', 0.0)),
                        'offset': pick(a, 'offset', 0.0),
                        'start': pick(a, 'start', 0.0),
                    }
                self.sources.append({'name': name, 'nodes': (p, q), **source})
                if str(a.get('CurrentFlag', 0)) == '1':
                    self.currents.append(('source', len(self.sources) - 1, name))
            elif t == 'VP':
                self.probes.append((name, self.node[ports(e)[0]]))
        self.nodes = count - 1
        self.size = self.nodes + len(self.sources)

    def emf(self, source, time):
        if source['kind'] == 'dc':
            return source['level']
        if time < source['start']:
            return source['offset']
        angle = 2 * math.pi * source['frequency'] * (time - source['start']) + source['phase']
        return source['offset'] + source['peak'] * math.sin(angle)

    def matrix(self, initial):
        """initial=True 求 t=0 的一致初值：电容视作 0 V 电压源，电感视作 0 A 电流源。"""
        n = self.size + (sum(p['type'] == 'C' for p in self.passives) if initial else 0)
        m = [[0.0] * n for _ in range(n)]
        if initial:
            # t=0 时电感按开路处理，只经电感相连的节点会悬空：对地加极小电导（与 SPICE 的 gmin 同理）。
            for k in range(self.nodes):
                m[k][k] += 1e-12

        def stamp(a, b, g):
            for i, j, s in ((a, a, g), (b, b, g), (a, b, -g), (b, a, -g)):
                if i and j:
                    m[i - 1][j - 1] += s

        def branch(row, a, b):
            if a:
                m[a - 1][row] += 1
                m[row][a - 1] += 1
            if b:
                m[b - 1][row] -= 1
                m[row][b - 1] -= 1

        for k, source in enumerate(self.sources):
            branch(self.nodes + k, *source['nodes'])
        extra = self.size
        for part in self.passives:
            a, b = part['nodes']
            if part['type'] == 'R':
                stamp(a, b, 1 / part['value'])
            elif initial and part['type'] == 'C':
                branch(extra, a, b)
                extra += 1
            elif not initial:
                g = 2 * part['value'] / self.step if part['type'] == 'C' else self.step / (2 * part['value'])
                stamp(a, b, g)
        return m

    def run(self):
        # t = 0：一致初值（电容电压 0、电感电流 0，与 PSIM 默认的零初始状态一致）。
        factored = lu(self.matrix(True))
        rhs = [0.0] * len(factored[0])
        for k, source in enumerate(self.sources):
            rhs[self.nodes + k] = self.emf(source, 0.0)
        x = solve(factored, rhs)
        state = []
        caps = iter(range(self.size, len(x)))
        for part in self.passives:
            a, b = part['nodes']
            v = (x[a - 1] if a else 0.0) - (x[b - 1] if b else 0.0)
            if part['type'] == 'C':
                # 支路电流按 MNA 约定从第一个端口经元件流向第二个端口。
                state.append({'v': 0.0, 'i': x[next(caps)]})
            elif part['type'] == 'L':
                state.append({'v': v, 'i': 0.0})
            else:
                state.append({'v': v, 'i': v / part['value']})
        factored = lu(self.matrix(False))
        steps = round(self.total / self.step)
        columns = ['Time'] + [name for name, _ in self.probes] + [f'I({name})' for _, _, name in self.currents]
        rows = []
        for n in range(1, steps + 1):
            time = n * self.step
            rhs = [0.0] * self.size
            for k, source in enumerate(self.sources):
                rhs[self.nodes + k] = self.emf(source, time)
            history = []
            for part, s in zip(self.passives, state):
                a, b = part['nodes']
                if part['type'] == 'R':
                    history.append(0.0)
                    continue
                if part['type'] == 'C':
                    g = 2 * part['value'] / self.step
                    source = -(g * s['v'] + s['i'])
                else:
                    g = self.step / (2 * part['value'])
                    source = s['i'] + g * s['v']
                history.append(source)
                # 支路电流 i = g·v + source，从 a 流向 b：移到右端即 a 处减、b 处加。
                if a:
                    rhs[a - 1] -= source
                if b:
                    rhs[b - 1] += source
            x = solve(factored, rhs)
            for part, s, source in zip(self.passives, state, history):
                a, b = part['nodes']
                v = (x[a - 1] if a else 0.0) - (x[b - 1] if b else 0.0)
                if part['type'] == 'R':
                    s.update(v=v, i=v / part['value'])
                else:
                    g = 2 * part['value'] / self.step if part['type'] == 'C' else self.step / (2 * part['value'])
                    s.update(v=v, i=g * v + source)
            if time + 1e-12 * self.step < self.print_time or n % self.print_step:
                continue
            row = [time] + [(x[node - 1] if node else 0.0) for _, node in self.probes]
            for where, index, _ in self.currents:
                # 电压源电流按 MNA 约定从正端经电源内部流向负端，取反后为从第一个端口流出。
                row.append(state[index]['i'] if where == 'passive' else -x[self.nodes + index])
            rows.append(row)
        return columns, rows


def checks(circuit):
    """步长与时长的经验检查：步长相对最快时间常数是否够细，时长是否覆盖到稳态。"""
    findings, taus = [], []
    if circuit.uncalibrated:
        findings.append(
            {
                'severity': 'info',
                'code': 'PORTS_UNCALIBRATED',
                'message': '以下元件的端口位置还没有用原生导出标定，预仿真按假设的端口连接：'
                + '、'.join(circuit.uncalibrated),
                'hint': '在 Windows 上核对原生网表，或先用小电路标定端口。',
            }
        )
    resistance = [p['value'] for p in circuit.passives if p['type'] == 'R']
    for p in circuit.passives:
        if p['type'] == 'C' and resistance:
            taus += [p['value'] * r for r in resistance]
        if p['type'] == 'L' and resistance:
            taus += [p['value'] / r for r in resistance]
    if taus:
        fast, slow = min(taus), max(taus)
        if circuit.step > fast / 20:
            findings.append(
                {
                    'severity': 'warning',
                    'code': 'TIMESTEP_COARSE',
                    'message': f'步长 {circuit.step:g}s 大于最小 RC/LR 时间常数 {fast:g}s 的 1/20',
                    'hint': '把 TIMESTEP 减到时间常数的 1/50 左右，或核对元件值。',
                }
            )
        if circuit.total < 5 * slow:
            findings.append(
                {
                    'severity': 'info',
                    'code': 'TOTALTIME_SHORT',
                    'message': f'总时长 {circuit.total:g}s 小于最大时间常数 {slow:g}s 的 5 倍，波形可能还没到稳态',
                    'hint': '需要稳态值时加长 TOTALTIME。',
                }
            )
    for source in circuit.sources:
        if source['kind'] == 'sin' and source['frequency'] > 0 and circuit.step > 1 / source['frequency'] / 200:
            findings.append(
                {
                    'severity': 'warning',
                    'code': 'TIMESTEP_COARSE',
                    'message': f'{source["name"]} 每周期不足 200 个步长',
                    'hint': '减小 TIMESTEP。',
                }
            )
    return findings


def presimulate(plan, target):
    circuit = Circuit(plan)
    columns, rows = circuit.run()
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows([f'{v:.10g}' for v in row] for row in rows)
    summary = {}
    for k, name in enumerate(columns[1:], 1):
        values = [row[k] for row in rows]
        summary[name] = {'final': values[-1], 'min': min(values), 'max': max(values)} if values else {}
    return {
        'csv': str(target.resolve()),
        'source': 'portable_presim',
        'native_verified': False,
        'method': '节点分析 + 固定步长梯形积分（与 PSIM 相同的算法类别）；零初始状态',
        'timestep': circuit.step,
        'samples': len(rows),
        'columns': columns,
        'summary': summary,
        'findings': checks(circuit),
        'note': '离线预仿真，不是 PSIM 求解结果；交付波形须来自 PSIM。',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', type=Path)
    parser.add_argument('csv', type=Path)
    args = parser.parse_args()
    try:
        if args.csv.suffix.lower() != '.csv':
            raise ValueError('输出须为 .csv')
        result = presimulate(json.loads(args.plan.read_text(encoding='utf-8-sig')), args.csv)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
