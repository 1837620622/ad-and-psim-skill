"""Mac/Linux 上仿原生出图、文字定位模型、离线预仿真与预检的可移植验证。

仿原生出图与仓库里的 Windows 原生导出（docs/images/*-native-rc.png）逐像素比较；没有 Pillow 或
Times New Roman/Arial（及同度量字体）时跳过。
"""

from contextlib import contextmanager
import csv
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout'
PSIM = ROOT / 'skills/psim-simulation-layout'
HAS_PILLOW = importlib.util.find_spec('PIL') is not None


@contextmanager
def load(skill, *names):
    """在独立的模块表里加载某个技能的脚本（两个技能有同名模块），退出时恢复。"""
    saved = {name: sys.modules.pop(name) for name in list(sys.modules) if name in SKILL_MODULES}
    sys.path.insert(0, str(skill / 'scripts'))
    try:
        yield [__import__(name) for name in names]
    finally:
        sys.path.remove(str(skill / 'scripts'))
        for name in SKILL_MODULES:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


SKILL_MODULES = (
    'canvas',
    'render',
    'psim_plan',
    'presim',
    'native_ad',
    'native_psim',
    'plan_tools',
    'schdoc',
    'tidy_wires',
    'check_layout',
    'compare_results',
    'native_job',
)


def stroke_alignment(native, portable):
    """只看线条和文字（不算白底）：在 1 像素内与原生图对齐的比例；尺寸不同时返回 0。"""
    from PIL import Image

    a, b = Image.open(native).convert('RGB'), Image.open(portable).convert('RGB')
    if a.size != b.size:
        return a.size, b.size, 0.0
    pa, pb = a.load(), b.load()
    width, height = a.size

    def ink(c):
        return sum(c) < 700

    union = aligned = 0
    for y in range(height):
        for x in range(width):
            mine = ink(pb[x, y])
            if not (ink(pa[x, y]) or mine):
                continue
            union += 1
            neighbours = (
                ink(pa[x + i, y + j])
                for i in (-1, 0, 1)
                for j in (-1, 0, 1)
                if 0 <= x + i < width and 0 <= y + j < height
            )
            aligned += any(n == mine for n in neighbours)
    return a.size, b.size, aligned / union


def plan(skill):
    return json.loads((skill / 'assets/rc-filter-plan.json').read_text(encoding='utf-8'))


@unittest.skipUnless(HAS_PILLOW, 'Pillow 未安装')
class NativeLook(unittest.TestCase):
    def test_ad_render_matches_windows_export(self):
        with (
            load(AD, 'canvas', 'native_ad', 'render') as (canvas, native_ad, render),
            tempfile.TemporaryDirectory() as d,
        ):
            if not canvas.gdi_available():
                self.skipTest('没有 Times New Roman 或同度量字体')
            result = render.render_records(native_ad.build(plan(AD)).records, Path(d) / 'a.png')
            self.assertEqual(result['renderer'], 'gdi')
            size, rendered, same = stroke_alignment(ROOT / 'docs/images/ad-native-rc.png', result['render'])
        self.assertEqual(size, rendered)
        self.assertGreater(same, 0.95)

    def test_psim_render_matches_windows_export(self):
        with load(PSIM, 'canvas', 'render') as (canvas, render), tempfile.TemporaryDirectory() as d:
            if not canvas.gdi_available():
                self.skipTest('没有 Arial 或同度量字体')
            result = render.render_plan(plan(PSIM), Path(d) / 'p.png')
            size, rendered, same = stroke_alignment(ROOT / 'docs/images/psim-native-rc.png', result['render'])
        self.assertEqual(size, rendered)
        self.assertGreater(same, 0.95)

    def test_render_does_not_depend_on_pillow_layout_engine(self):
        # Mac 上的 Pillow 常没有 raqm，只能用 basic 引擎；两种引擎画出的图必须逐字节相同。
        from PIL import ImageFont

        truetype = ImageFont.truetype

        def basic(*args, **kwargs):
            return truetype(*args, layout_engine=ImageFont.Layout.BASIC, **kwargs)

        with load(PSIM, 'canvas', 'render') as (canvas, render), tempfile.TemporaryDirectory() as d:
            if not canvas.gdi_available():
                self.skipTest('没有 Arial 或同度量字体')
            default = Path(render.render_plan(plan(PSIM), Path(d) / 'default.png')['render']).read_bytes()
            ImageFont.truetype = basic
            try:
                forced = Path(render.render_plan(plan(PSIM), Path(d) / 'basic.png')['render']).read_bytes()
            finally:
                ImageFont.truetype = truetype
        self.assertEqual(default, forced)

    def test_svg_and_explicit_backends_are_unchanged(self):
        with load(PSIM, 'render') as (render,), tempfile.TemporaryDirectory() as d:
            self.assertEqual(render.render_plan(plan(PSIM), Path(d) / 'p.svg')['renderer'], 'svg')
            self.assertEqual(render.render_plan(plan(PSIM), Path(d) / 'p.png', renderer='pillow')['renderer'], 'pillow')


class PsimTextModel(unittest.TestCase):
    # Windows 原生导出里实测的文字墨迹框（计划坐标）：位号、参数、探头名。
    NATIVE = {
        ('V1', 'Name'): (109.3, 106.1, 122.8, 115.8),
        ('V1', 'Amplitude'): (114.5, 122.8, 126.0, 132.5),
        ('R1', 'Name'): (157.6, 57.2, 170.4, 66.9),
        ('R1', 'Resistance'): (160.8, 74.0, 180.7, 83.6),
        ('C1', 'Name'): (263.0, 110.0, 277.2, 119.6),
        ('Vout', 'Name'): (268.2, 74.0, 293.9, 83.6),
        ('Vin', 'Name'): (113.2, 74.0, 129.9, 83.6),
    }

    def test_text_positions_follow_native_rule(self):
        with load(PSIM, 'psim_plan') as (psim_plan,):
            for item in plan(PSIM)['elements']:
                for label in item.get('textlinks', []):
                    measured = self.NATIVE.get((item['name'], label['FieldName']))
                    if measured is None:
                        continue
                    predicted = psim_plan.text_box(item, label)
                    with self.subTest(text=(item['name'], label['FieldName'])):
                        self.assertAlmostEqual(predicted[0], measured[0], delta=2)
                        self.assertAlmostEqual(predicted[1], measured[1], delta=1)
                        self.assertAlmostEqual(predicted[2], measured[2], delta=3)

    def test_text_too_close_to_a_source_is_reported(self):
        crowded = plan(PSIM)
        source = next(e for e in crowded['elements'] if e.get('name') == 'V1')
        label = source['textlinks'][1]
        x1, y1, x2, y2 = label['AREA']
        label['AREA'] = [x1 - 14, y1, x2 - 14, y2]
        with load(PSIM, 'check_layout') as (check_layout,):
            codes = {f['code'] for f in check_layout.check_plan(crowded)['findings']}
        self.assertIn('TEXT_ON_SYMBOL', codes)


def element(kind, name, port, **attributes):
    return {'type': kind, 'name': name, 'attributes': {'PORTS': port, 'DIRECTION': 0, **attributes}}


def series_plan(source, part, probe_at, step='1e-6', total='0.002', flag=False):
    """电源 (100,100)-(100,150)，串联元件 (150,100)-(200,100)，后接电阻或电容到地。"""
    first, second = part
    elements = [
        {'type': 'SIMCONTROL', 'name': '', 'attributes': {'POINT': '{40,50}', 'TIMESTEP': step, 'TOTALTIME': total}},
        source,
        dict(first, attributes=dict(first['attributes'], **({'CurrentFlag': 1} if flag else {}))),
        second,
        {'type': 'Ground', 'name': 'GND', 'attributes': {'PORTS': '{100,150}', 'DIRECTION': 0}},
        element('VP', 'Vout', probe_at),
    ]
    for x1, y1, x2, y2 in ((100, 100, 150, 100), (200, 100, 250, 100), (100, 150, 250, 150)):
        elements.append({'type': 'WIRE', 'name': '', 'attributes': {'X1': x1, 'Y1': y1, 'X2': x2, 'Y2': y2}})
    return {'elements': elements}


class PreSimulation(unittest.TestCase):
    def run_plan(self, data):
        with load(PSIM, 'presim') as (presim,), tempfile.TemporaryDirectory() as d:
            result = presim.presimulate(data, Path(d) / 'out.csv')
            with open(result['csv'], encoding='utf-8') as stream:
                result['rows'] = list(csv.DictReader(stream))
        return result

    @staticmethod
    def column(result, name):
        return [float(r['Time']) for r in result['rows']], [float(r[name]) for r in result['rows']]

    def test_rc_step_matches_analytic_solution(self):
        result = self.run_plan(plan(PSIM))
        self.assertEqual(result['samples'], 2000)
        times, vout = self.column(result, 'Vout')
        self.assertAlmostEqual(times[0], 1e-6)
        error = max(abs(v - 10 * (1 - math.exp(-t / 1e-4))) for t, v in zip(times, vout))
        self.assertLess(error, 1e-4)
        _, current = self.column(result, 'I(R1)')
        self.assertAlmostEqual(current[0], (10 - vout[0]) / 100, places=9)

    def test_rl_step_current(self):
        data = series_plan(
            element('VDC', 'V1', '{100,100}', Amplitude=10),
            (
                element('L', 'L1', '{150,100}', Inductance='1m'),
                {'type': 'R', 'name': 'R1', 'attributes': {'PORTS': '{250,100}', 'DIRECTION': 90, 'Resistance': 10}},
            ),
            '{250,100}',
            flag=True,
        )
        times, current = self.column(self.run_plan(data), 'I(L1)')
        error = max(abs(i - (1 - math.exp(-t / 1e-4))) for t, i in zip(times, current))
        self.assertLess(error, 1e-4)

    def test_sine_steady_state_amplitude(self):
        data = series_plan(
            element('VSIN', 'V1', '{100,100}', Amplitude=1, Frequency='1k'),
            (
                element('R', 'R1', '{150,100}', Resistance='1k'),
                {'type': 'C', 'name': 'C1', 'attributes': {'PORTS': '{250,100}', 'DIRECTION': 90, 'Capacitance': '1u'}},
            ),
            '{250,100}',
            total='0.02',
        )
        times, vout = self.column(self.run_plan(data), 'Vout')
        last = [v for t, v in zip(times, vout) if t > 0.015]
        expected = 1 / math.sqrt(1 + (2 * math.pi * 1e3 * 1e3 * 1e-6) ** 2)
        self.assertAlmostEqual(max(last), expected, delta=2e-3)

    def test_unsupported_elements_are_refused(self):
        data = plan(PSIM)
        data['elements'].append(element('MOSFET', 'Q1', '{400,100}'))
        with self.assertRaisesRegex(ValueError, 'MOSFET'):
            self.run_plan(data)

    def test_coarse_timestep_is_reported(self):
        data = plan(PSIM)
        control = next(e for e in data['elements'] if e['type'] == 'SIMCONTROL')
        control['attributes'].update(TIMESTEP='2e-5', TOTALTIME='0.002')
        codes = {f['code'] for f in self.run_plan(data)['findings']}
        self.assertIn('TIMESTEP_COARSE', codes)

    def test_values_use_psim_suffixes(self):
        with load(PSIM, 'presim') as (presim,):
            self.assertEqual(presim.value('4.7k'), 4700)
            self.assertAlmostEqual(presim.value('100m'), 0.1)
            self.assertEqual(presim.value('2M'), 2e6)
            with self.assertRaises(ValueError):
                presim.value('1 farad')


class TextPlacement(unittest.TestCase):
    def test_ad_overlapping_labels_are_errors_and_get_placed(self):
        with load(AD, 'plan_tools') as (plan_tools,):
            crowded = plan_tools.apply_edits(
                plan(AD),
                [
                    {'op': 'move_text', 'ref': 'R1', 'field': 'designator', 'at': [125, 152]},
                    {'op': 'move_text', 'ref': 'C1', 'field': 'comment', 'at': [236, 125]},
                    {'op': 'move_text', 'ref': 'J2', 'field': 'comment', 'at': [262, 150]},
                ],
            )
            problems = plan_tools._text_problems(crowded)[0]
            self.assertIn('error', {f['severity'] for f in problems if f['code'] == 'TEXT_OVERLAP'})
            placed = plan_tools.apply_edits(crowded, [{'op': 'place_text'}])
            self.assertEqual(plan_tools._text_problems(placed)[0], [])
            self.assertEqual(plan_tools.apply_edits(plan(AD), [{'op': 'place_text'}]), plan(AD))

    def test_psim_overlapping_labels_are_errors_and_get_placed(self):
        crowded = plan(PSIM)
        for item in crowded['elements']:
            if item.get('name') == 'R1':
                item['textlinks'][0]['AREA'] = [160, 88, 190, 105]
            if item.get('name') == 'Vout':
                item['textlinks'][0]['AREA'] = [116, 72, 146, 89]
        with load(PSIM, 'psim_plan', 'check_layout') as (psim_plan, check_layout):
            result = check_layout.check_plan(crowded)
            self.assertFalse(result['summary']['passed'])
            self.assertIn('TEXT_OVERLAP', {f['code'] for f in result['findings'] if f['severity'] == 'error'})
            placed = psim_plan.apply_edits(crowded, [{'op': 'place_text'}])
            self.assertEqual(psim_plan._text_problems(placed), [])
            self.assertEqual(check_layout.check_plan(placed)['summary']['warnings'], 0)
            self.assertEqual(psim_plan.apply_edits(plan(PSIM), [{'op': 'place_text'}]), plan(PSIM))

    def test_ad_text_touching_a_wire_is_reported_and_moved_away(self):
        with load(AD, 'plan_tools') as (plan_tools,):
            # 墨迹底边约在 y=149.98，紧贴 y=150 的导线但不压线。
            touching = plan_tools.apply_edits(
                plan(AD), [{'op': 'move_text', 'ref': 'R1', 'field': 'comment', 'at': [210, 148]}]
            )
            problems = plan_tools._text_problems(touching)[0]
            self.assertEqual([(f['code'], f['severity']) for f in problems], [('TEXT_NEAR_LINE', 'warning')])
            placed = plan_tools.apply_edits(touching, [{'op': 'place_text'}])
            self.assertEqual(plan_tools._text_problems(placed)[0], [])

    def test_ad_text_outside_the_border_is_moved_back(self):
        with load(AD, 'plan_tools', 'check_layout') as (plan_tools, check_layout):
            outside = plan_tools.apply_edits(
                plan(AD), [{'op': 'move_text', 'ref': 'J1', 'field': 'designator', 'at': [14, 155]}]
            )
            self.assertIn('OUTSIDE_BORDER', {f['code'] for f in check_layout.check_plan(outside)['findings']})
            placed = plan_tools.apply_edits(outside, [{'op': 'place_text'}])
            self.assertEqual(check_layout.check_plan(placed)['summary']['errors'], 0)
            self.assertEqual(plan_tools._text_problems(placed)[0], [])

    def test_ad_horizontal_power_names_read_away_from_the_symbol(self):
        # 朝右、朝左的电源名称在符号末端外侧（与 render.py 一致），不能被当成压着自己的符号。
        sideways = plan(AD)
        sideways['canvas'] = [420, 300]
        for x, orientation, sign in ((100, 0, -1), (300, 2, 1)):
            for y, ground in ((220, False), (260, True)):
                sideways['power_ports'].append(
                    {'name': 'PGND' if ground else 'VCC5', 'at': [x, y], 'ground': ground, 'orientation': orientation}
                )
                sideways['wires'].append([[x, y], [x + 40 * sign, y]])
        with load(AD, 'check_layout') as (check_layout,):
            findings = check_layout.check_plan(sideways)['findings']
            self.assertEqual([f for f in findings if f['code'].startswith('TEXT')], [])
            sideways['wires'].append([[125, 210], [125, 230]])
            codes = {f['code'] for f in check_layout.check_plan(sideways)['findings']}
            self.assertIn('TEXT_ON_GRAPHICS', codes)

    def test_ad_place_text_all_restores_standard_positions(self):
        with load(AD, 'plan_tools') as (plan_tools,):
            # 两处文字挪开但互不冲突：普通 place_text 不动，all 放回标准位置。
            scattered = plan_tools.apply_edits(
                plan(AD),
                [
                    {'op': 'move_text', 'ref': 'R1', 'field': 'designator', 'at': [100, 180]},
                    {'op': 'move_text', 'ref': 'C1', 'field': 'comment', 'at': [260, 100]},
                ],
            )
            self.assertEqual(plan_tools.apply_edits(scattered, [{'op': 'place_text'}]), scattered)
            self.assertEqual(plan_tools.apply_edits(scattered, [{'op': 'place_text', 'all': True}]), plan(AD))

    def test_psim_text_touching_a_wire_is_reported_and_moved_away(self):
        touching = plan(PSIM)
        for item in touching['elements']:
            if item.get('name') == 'R1':
                # 文字底边约在 y=149.4，紧贴 y=150 的地线但不压线。
                item['textlinks'][1]['AREA'] = [160, 138, 195, 155]
        with load(PSIM, 'psim_plan', 'check_layout') as (psim_plan, check_layout):
            findings = check_layout.check_plan(touching)['findings']
            self.assertEqual([(f['code'], f['severity']) for f in findings], [('TEXT_NEAR_LINE', 'warning')])
            placed = psim_plan.apply_edits(touching, [{'op': 'place_text'}])
            self.assertEqual(check_layout.check_plan(placed)['summary']['warnings'], 0)

    def test_psim_label_blocked_by_neighbours_is_placed_after_resetting_them(self):
        # Vout 的名称压着探头；探头右侧和左侧的空位分别被 C1、R1 的文字占着，单独挪 Vout 挪不开。
        blocked = plan(PSIM)
        for item in blocked['elements']:
            if item.get('name') == 'C1':
                item['textlinks'][0]['AREA'] = [265, 72, 298, 89]
            if item.get('name') == 'R1':
                item['textlinks'][1]['AREA'] = [205, 72, 240, 89]
            if item.get('name') == 'Vout':
                item['textlinks'][0]['AREA'] = [236, 80, 266, 97]
        with load(PSIM, 'psim_plan', 'check_layout') as (psim_plan, check_layout):
            codes = [f['code'] for f in check_layout.check_plan(blocked)['findings']]
            self.assertEqual(codes, ['TEXT_ON_SYMBOL'])
            placed = psim_plan.apply_edits(blocked, [{'op': 'place_text'}])
            self.assertEqual(check_layout.check_plan(placed)['findings'], [])

    def test_psim_place_text_all_uses_the_first_candidate(self):
        scattered = plan(PSIM)
        for item in scattered['elements']:
            if item.get('name') == 'R1':
                item['textlinks'][0]['AREA'] = [160, 112, 190, 129]
            if item.get('name') == 'C1':
                item['textlinks'][1]['AREA'] = [266, 150, 296, 167]
        with load(PSIM, 'psim_plan', 'check_layout') as (psim_plan, check_layout):
            self.assertEqual(psim_plan.apply_edits(scattered, [{'op': 'place_text'}]), scattered)
            placed = psim_plan.apply_edits(scattered, [{'op': 'place_text', 'all': True}])
            self.assertEqual(check_layout.check_plan(placed)['summary']['warnings'], 0)
            areas = {
                item['name']: [link['AREA'] for link in item['textlinks']]
                for item in placed['elements']
                if item.get('textlinks')
            }
        # 横放的 R1 两段文字都在符号上方，竖放的 C1 都在右侧。
        self.assertTrue(all(area[3] <= 93 for area in areas['R1']))
        self.assertTrue(all(area[0] >= 260 for area in areas['C1']))


class Preflight(unittest.TestCase):
    def test_ad_predicts_native_compile_result(self):
        with load(AD, 'native_ad') as (native_ad,), tempfile.TemporaryDirectory() as d:
            result = native_ad.preflight(plan(AD), d)
        self.assertTrue(result['ready_for_windows'])
        # Windows 实测：0 error、4 条缺少封装的 warning（docs/VALIDATION.md）。
        self.assertEqual(result['expected_native']['compile_errors'], 0)
        self.assertEqual(result['expected_native']['compile_warnings_missing_footprint'], 4)
        self.assertTrue(result['expected_native']['netlist_matches_pin_map'])

    def test_psim_runs_check_preview_and_presim(self):
        with load(PSIM, 'native_psim') as (native_psim,), tempfile.TemporaryDirectory() as d:
            result = native_psim.preflight(plan(PSIM), d)
            self.assertTrue(Path(result['preview']).is_file())
        self.assertTrue(result['ready_for_windows'])
        self.assertEqual(result['presim']['samples'], 2000)

    def test_presim_forecast_is_compared_with_native_waveforms(self):
        with load(PSIM, 'native_job') as (native_job,), tempfile.TemporaryDirectory() as d:
            presim, native = Path(d, 'presim.csv'), Path(d, 'native.csv')
            presim.write_text('Time,Vout\n1e-06,0.0995\n2e-06,0.198\n', encoding='utf-8')
            native.write_text('Time,Vout\n1e-06,0.0996\n2e-06,0.198\n', encoding='utf-8')
            result = native_job._forecast_psim(presim, {'csv': str(native), 'columns': ['Time', 'Vout']})
        self.assertEqual(result['agreement'], 'within_tolerance')
        self.assertAlmostEqual(result['signals']['Vout'], 1e-4)


if __name__ == '__main__':
    unittest.main()
