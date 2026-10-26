"""排版预检、原生写入几何、EMF 压线审查与技能元数据的可移植检查。"""
import copy
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout'
PSIM = ROOT / 'skills/psim-simulation-layout'
sys.path[:0] = [str(AD / 'scripts'), str(Path(__file__).resolve().parent)]
import ad_document  # noqa: E402
import check_layout as ad_check  # noqa: E402
import native_ad  # noqa: E402
from emf_builder import ellipse, emf, polyline16, set_extent, set_map_mode, text  # noqa: E402
from review_emf_text import review  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


psim_check = load(PSIM / 'scripts/check_layout.py', 'psim_check_layout')
AD_PLAN = json.loads((AD / 'assets/rc-filter-plan.json').read_text(encoding='utf-8'))
PSIM_PLAN = json.loads((PSIM / 'assets/rc-filter-plan.json').read_text(encoding='utf-8'))


def codes(result, severity=None):
    return {f['code'] for f in result['findings'] if severity in (None, f['severity'])}


class AdGeometry(unittest.TestCase):
    def test_passive_hot_ends_on_grid_for_any_scale(self):
        for scale in (.25, .375, .5, .625, .75, 1, 1.5):
            for vertical in (False, True):
                for kind in 'RCLY':
                    sheet = ad_document.Sheet()
                    sheet.passive('X1', '1', 300, 200, vertical=vertical, kind=kind, scale=scale)
                    ends = [ad_document.pin_end(r) for r in sheet.records if r.get('RECORD') == '2']
                    self.assertTrue(all(v % 10 == 0 for end in ends for v in end), (scale, vertical, kind, ends))

    def test_part_text_uses_one_font(self):
        sheet = native_ad.build(AD_PLAN)
        fonts = {r['FONTID'] for r in sheet.records if r.get('RECORD') in ('34', '41')}
        self.assertEqual(fonts, {'1'})

    def test_tidy_cuts_rail_at_pin_and_marks_t_junction(self):
        plan = {'units': '10mil', 'canvas': [300, 200],
                'parts': [{'kind': 'C', 'ref': 'C1', 'value': '1nF', 'at': [150, 120], 'vertical': True}],
                'wires': [[[100, 100], [200, 100]]]}
        records = native_ad.build(plan).records
        wires = [(r['X1'], r['X2']) for r in records if r.get('RECORD') == '27']
        junctions = [(r['LOCATION.X'], r['LOCATION.Y']) for r in records if r.get('RECORD') == '29']
        self.assertEqual(sorted(wires), [('100', '150'), ('150', '200')])
        self.assertEqual(junctions, [('150', '100')])

    def test_compound_file_unused_entries_use_nostream(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.SchDoc'
            ad_document.write_compound(path, {'FileHeader': b'abc', 'Storage': b'', 'Additional': b'd'})
            raw = path.read_bytes()
            directory = struct.unpack_from('<I', raw, 48)[0]
            sector = raw[512 * (directory + 1):512 * (directory + 2)]
            for index in range(4):
                entry = sector[index * 128:(index + 1) * 128]
                if entry[66] == 0:
                    self.assertEqual(struct.unpack_from('<III', entry, 68), (0xffffffff,) * 3)


class AdLayoutCheck(unittest.TestCase):
    def check(self, mutate):
        plan = copy.deepcopy(AD_PLAN)
        mutate(plan)
        return ad_check.check_plan(plan)

    def test_example_is_clean_and_matches_pin_map(self):
        result = ad_check.check_plan(AD_PLAN)
        self.assertEqual((result['summary']['errors'], result['summary']['warnings']), (0, 0), result['findings'])
        self.assertTrue(result['topology']['match'])
        self.assertGreater(result['metrics']['fill_ratio'], .3)

    def test_structural_mistakes_are_errors(self):
        cases = {
            'DANGLING_WIRE': lambda p: p['wires'].append([[240, 150], [240, 190]]),
            'LABEL_FLOATING': lambda p: p['labels'].append({'name': 'VOUT', 'at': [270, 170]}),
            'PIN_OFF_GRID': lambda p: p['parts'][1].__setitem__('at', [185, 150]),
            'TEXT_ENCODING': lambda p: p['parts'][2].__setitem__('value', '0.1µF'),
        }
        for code, mutate in cases.items():
            self.assertIn(code, codes(self.check(mutate), 'error'), code)

    def test_accidental_short_breaks_predicted_topology(self):
        def short(plan):
            plan['parts'][2]['at'] = [140, 130]
            plan['wires'][2] = [[140, 150], 'C1.1']
        result = self.check(short)
        self.assertIn('TOPOLOGY_MISMATCH', codes(result, 'error'))

    def test_visual_mistakes_are_warnings(self):
        cases = {
            'TEXT_OVERLAP': lambda p: p['labels'].append({'name': 'VIN_SENSE', 'at': [130, 150]}),
            'WIRE_THROUGH_BODY': lambda p: p['wires'].extend([[[180, 140], [180, 170]], [[170, 140], [190, 140]]]),
            'FOUR_WAY_JUNCTION': lambda p: (p['wires'].append([[240, 150], [240, 170]]),
                                            p['labels'].append({'name': 'VOUT', 'at': [240, 170]})),
            'FLOATING_TITLE': lambda p: p.__setitem__('texts', [{'text': 'RC FILTER', 'at': [180, 190], 'font': 3}]),
            'SPARSE_SHEET': lambda p: p.__setitem__('canvas', [900, 600]),
            'VALUE_FORMAT': lambda p: p['parts'][2].__setitem__('value', '1e-07'),
            'POWER_ORIENTATION': lambda p: p['power_ports'][1].__setitem__('orientation', 1),
        }
        for code, mutate in cases.items():
            self.assertIn(code, codes(self.check(mutate)), code)

    def test_create_refuses_layout_errors_unless_allowed(self):
        plan = copy.deepcopy(AD_PLAN)
        plan['wires'].append([[240, 150], [240, 190]])
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                native_ad.create(plan, Path(folder) / 'a')
            result = native_ad.create(plan, Path(folder) / 'b', allow_layout_errors=True)
            self.assertFalse(result['layout_check']['passed'])

    def test_create_writes_project_and_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            result = native_ad.create(AD_PLAN, folder)
            self.assertTrue(result['layout_check']['passed'])
            for name in ('RC_Filter.SchDoc', 'RC_Filter.PrjPcb', 'expected.json', 'layout-check.json'):
                self.assertTrue((Path(folder) / name).is_file(), name)

    def test_preview_renders_when_pillow_available(self):
        if importlib.util.find_spec('PIL') is None:
            self.skipTest('Pillow 未安装')
        with tempfile.TemporaryDirectory() as folder:
            result = ad_check.check_plan(AD_PLAN, Path(folder) / 'draft.png')
            self.assertTrue(Path(result['preview']['preview']).is_file())


class EmfTextReview(unittest.TestCase):
    def test_line_through_text_is_reported(self):
        result = review(emf(text('VOUT', (100, 100, 160, 120)), polyline16([(90, 110), (170, 110)])))
        self.assertEqual(len(result['text_line_conflicts']), 1)

    def test_line_in_descender_zone_is_not_reported(self):
        result = review(emf(text('VOUT', (100, 100, 160, 120)), polyline16([(90, 119), (170, 119)])))
        self.assertEqual(result['text_line_conflicts'], [])

    def test_single_digit_above_pin_line_is_not_reported(self):
        self.assertEqual(review(emf(text('1', (100, 100, 108, 118)), polyline16([(90, 118), (130, 118)])))
                         ['text_line_conflicts'], [])
        self.assertEqual(len(review(emf(text('1', (100, 100, 108, 118)), polyline16([(90, 109), (130, 109)])))
                             ['text_line_conflicts']), 1)

    def test_mapping_mode_is_applied(self):
        raw = emf(set_map_mode(8), set_extent(9, 1000, 1000), set_extent(11, 100, 100),
                  text('R1', (100, 100, 130, 120)), polyline16([(900, 1100), (1400, 1100)], (90, 110, 140, 110)))
        result = review(raw)
        self.assertTrue(result['line_check']['transform_reliable'])
        self.assertEqual(len(result['text_line_conflicts']), 1)

    def test_circle_touching_text(self):
        self.assertEqual(len(review(emf(text('Vin', (100, 100, 130, 120)), ellipse((110, 108, 150, 148))))
                             ['text_line_conflicts']), 1)
        self.assertEqual(review(emf(text('Vin', (100, 100, 130, 120)), ellipse((110, 125, 150, 165))))
                         ['text_line_conflicts'], [])

    def test_both_skills_ship_the_same_reviewer(self):
        self.assertEqual((AD / 'scripts/review_emf_text.py').read_bytes(),
                         (PSIM / 'scripts/review_emf_text.py').read_bytes())


class PsimLayoutCheck(unittest.TestCase):
    def test_example_is_clean(self):
        result = psim_check.check_plan(PSIM_PLAN)
        self.assertEqual((result['summary']['errors'], result['summary']['warnings']), (0, 0), result['findings'])

    def test_known_defects_are_reported(self):
        plan = copy.deepcopy(PSIM_PLAN)
        for e in plan['elements']:
            if e['type'] == 'SIMCONTROL':
                e['attributes']['POINT'] = '{100,40}'
            if e['name'] == 'Vin':
                e['textlinks'][0]['AREA'] = [80, 58, 120, 75]
            if e['name'] == 'C1':
                e['attributes']['Capacitance'] = 1e-06
            if e['name'] == 'R1':
                e['textlinks'][1]['AREA'] = [160, 83, 210, 100]
        found = codes(psim_check.check_plan(plan))
        self.assertTrue({'TEXT_ON_SYMBOL', 'SIMCONTROL_CROWDED', 'VALUE_FORMAT'} <= found, found)

    def test_diagonal_wire_is_error(self):
        plan = copy.deepcopy(PSIM_PLAN)
        plan['elements'].append({'type': 'WIRE', 'name': '', 'attributes': {'X1': 0, 'Y1': 0, 'X2': 10, 'Y2': 10}})
        self.assertIn('DIAGONAL_WIRE', codes(psim_check.check_plan(plan), 'error'))


class SkillMetadata(unittest.TestCase):
    def frontmatter(self, path):
        content = path.read_text(encoding='utf-8')
        match = re.match(r'---\n(.*?)\n---\n', content, re.S)
        self.assertIsNotNone(match, path)
        fields, key = {}, None
        for line in match.group(1).splitlines():
            if line.startswith('  ') and key:
                fields[key] = fields.get(key) or {}
                sub, _, value = line.strip().partition(':')
                fields[key][sub] = value.strip().strip('"')
            else:
                key, _, value = line.partition(':')
                fields[key] = value.strip().strip('"') or None
        return fields, content

    def test_agent_skills_spec(self):
        for folder in (AD, PSIM):
            fields, content = self.frontmatter(folder / 'SKILL.md')
            self.assertEqual(fields['name'], folder.name)
            self.assertRegex(fields['name'], r'^[a-z0-9]+(-[a-z0-9]+)*$')
            self.assertLessEqual(len(fields['description']), 1024)
            self.assertLessEqual(len(fields.get('compatibility') or ''), 500)
            self.assertLess(len(content.splitlines()), 500)
            for link in re.findall(r'\]\(([^)#]+)', content):
                if not link.startswith('http'):
                    self.assertTrue((folder / link).exists(), link)

    def test_json_assets_are_valid(self):
        for path in list(ROOT.glob('skills/*/assets/*.json')) + [ROOT / '.claude-plugin/plugin.json']:
            json.loads(path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
