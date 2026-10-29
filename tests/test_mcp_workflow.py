"""像 Agent 一样通过 MCP 修改当前图纸：导入、改参数、挪器件、改文字、自动摆放文字、重新生成、渲染、交付。

只用可移植工具（不需要 AD、PSIM）；一个服务器进程处理整段会话，与客户端的实际用法相同。
"""

import base64
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout'
PSIM = ROOT / 'skills/psim-simulation-layout'
PNG_BACKEND = any(importlib.util.find_spec(name) for name in ('PIL', 'resvg_py'))
TEXT_CODES = {'TEXT_OVERLAP', 'TEXT_ON_PART', 'TEXT_ON_GRAPHICS', 'TEXT_ON_SYMBOL', 'TEXT_ON_WIRE', 'TEXT_NEAR_LINE'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def codes(result):
    return {finding['code'] for finding in result['findings']}


class McpWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp())
        cls.log = (cls.work / 'server.log').open('w+b')
        cls.server = subprocess.Popen(
            [sys.executable, str(AD / 'scripts/mcp_server.py'), '--with', str(PSIM / 'scripts')],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=cls.log,
            cwd=ROOT,
        )
        cls.number = 0
        reply = cls.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}})
        assert reply['result']['serverInfo']['name'] == 'ad-and-psim-skill', reply
        cls.server.stdin.write(b'{"jsonrpc": "2.0", "method": "notifications/initialized"}\n')
        cls.tools = {tool['name'] for tool in cls.request('tools/list')['result']['tools']}

    @classmethod
    def tearDownClass(cls):
        cls.server.stdin.close()
        cls.server.wait(timeout=60)
        cls.log.close()
        shutil.rmtree(cls.work, ignore_errors=True)

    @classmethod
    def request(cls, method, params=None):
        cls.number += 1
        message = {'jsonrpc': '2.0', 'id': cls.number, 'method': method, 'params': params or {}}
        cls.server.stdin.write(json.dumps(message, ensure_ascii=False).encode('utf-8') + b'\n')
        cls.server.stdin.flush()
        line = cls.server.stdout.readline()
        if not line:
            cls.log.seek(0)
            raise AssertionError('MCP 服务器提前退出：' + cls.log.read().decode('utf-8', errors='replace'))
        reply = json.loads(line)
        assert reply['id'] == cls.number, reply
        return reply

    def call(self, tool, /, **arguments):
        self.assertIn(tool, self.tools)
        result = self.request('tools/call', {'name': tool, 'arguments': arguments})['result']
        texts = [item['text'] for item in result['content'] if item['type'] == 'text']
        images = [base64.b64decode(item['data']) for item in result['content'] if item['type'] == 'image']
        return json.loads(texts[0]), images, result.get('isError', False)

    def ok(self, tool, /, **arguments):
        data, images, failed = self.call(tool, **arguments)
        self.assertFalse(failed, f'{tool}: {data}')
        return data, images

    def picture(self, folder, stem):
        return str(folder / f'{stem}.png' if PNG_BACKEND else folder / f'{stem}.svg')

    def test_tool_list_covers_both_skills(self):
        self.assertEqual(len(self.tools), 33)
        self.assertTrue({'ad_import', 'ad_edit', 'psim_plan_edit', 'psim_waveforms', 'psim_deliver'} <= self.tools)

    def test_ad_edit_the_current_drawing(self):
        work = self.work / 'ad'
        self.ok('ad_create', plan=str(AD / 'assets/rc-filter-plan.json'), folder=str(work / 'v0'))
        self.ok('ad_import', schematic=str(work / 'v0/RC_Filter.SchDoc'), plan=str(work / 'current.json'))
        current = read(work / 'current.json')
        part = {p['ref']: p for p in current['parts']}

        # 改参数、挪器件、改位号，再把参数文字故意压到位号上。
        crowded = [
            {'op': 'set_value', 'ref': 'R1', 'value': '22k'},
            {'op': 'move', 'ref': 'C1', 'dx': 30},
            {'op': 'move_text', 'ref': 'R1', 'field': 'comment', 'at': part['R1']['designator_at']},
            {'op': 'rename', 'ref': 'R1', 'to': 'R10'},
        ]
        self.call('ad_edit', plan=str(work / 'current.json'), operations=crowded, output=str(work / 'crowded.json'))
        found, _, failed = self.call('ad_check', plan=str(work / 'crowded.json'))
        self.assertTrue(failed)
        self.assertIn('TEXT_OVERLAP', codes(found))

        # 自动摆放文字后预检回到 0 error、没有文字问题。
        fixed, _ = self.ok(
            'ad_edit',
            plan=str(work / 'crowded.json'),
            operations=json.dumps([{'op': 'place_text', 'all': True}]),
            output=str(work / 'fixed.json'),
        )
        self.assertEqual(fixed['layout_check']['errors'], 0)
        checked, images = self.ok('ad_check', plan=str(work / 'fixed.json'), preview=self.picture(work, 'draft'))
        self.assertTrue(checked['summary']['passed'])
        self.assertFalse(codes(checked) & TEXT_CODES)

        # 重新生成并读回：改动都在文件里，导线仍按 pin_map 连接。
        self.ok('ad_create', plan=str(work / 'fixed.json'), folder=str(work / 'v1'))
        _, images = self.ok('ad_render', source=str(work / 'v1/RC_Filter.SchDoc'), target=self.picture(work, 'view'))
        if PNG_BACKEND:
            self.assertTrue(images and images[0].startswith(b'\x89PNG'))
        self.ok('ad_import', schematic=str(work / 'v1/RC_Filter.SchDoc'), plan=str(work / 'back.json'))
        back = read(work / 'back.json')
        after = {p['ref']: p for p in back['parts']}
        self.assertNotIn('R1', after)
        self.assertEqual(after['R10']['value'], '22k')
        self.assertEqual(after['C1']['at'], [part['C1']['at'][0] + 30, part['C1']['at'][1]])
        self.assertNotEqual(after['R10']['comment_at'], after['R10']['designator_at'])
        self.assertTrue(self.ok('ad_check', plan=str(work / 'back.json'))[0]['summary']['passed'])

        # 交付：客户目录只有工程文件，计划 JSON 不进去；缓存被清理。
        (work / 'v1/__Previews').mkdir()
        (work / 'v1/RC_Filter.SchDocPreview').write_bytes(b'cache')
        delivered, _ = self.ok('ad_deliver', work=str(work / 'v1'), output=str(work / 'out'), name='RC', clean=True)
        self.assertEqual(sorted(delivered['delivered']), ['RC_Filter.PrjPcb', 'RC_Filter.SchDoc'])
        self.assertEqual(sorted(p.name for p in (work / 'out/RC').iterdir()), ['RC_Filter.PrjPcb', 'RC_Filter.SchDoc'])
        self.assertFalse((work / 'out/RC-archive').exists())
        self.assertIn('__Previews/', delivered['cleaned'])
        self.assertFalse((work / 'v1/RC_Filter.SchDocPreview').exists())

    def test_psim_edit_the_plan_and_draw_curves(self):
        work = self.work / 'psim'
        work.mkdir()
        plan = PSIM / 'assets/rc-filter-plan.json'
        elements = {e.get('name'): e for e in read(plan)['elements'] if e.get('name')}
        name, value = elements['R1']['textlinks'][:2]

        # 改参数、挪元件，再把参数文字故意挪到名称上。
        crowded = [
            {'op': 'set', 'name': 'R1', 'field': 'Resistance', 'value': '220'},
            {'op': 'move', 'name': 'C1', 'dx': 20},
            {'op': 'move_text', 'name': 'R1', 'field': 'Resistance', 'dy': name['AREA'][1] - value['AREA'][1]},
        ]
        self.call('psim_plan_edit', plan=str(plan), operations=crowded, output=str(work / 'crowded.json'))
        found, _, failed = self.call('psim_check', plan=str(work / 'crowded.json'))
        self.assertTrue(failed)
        self.assertIn('TEXT_OVERLAP', codes(found))

        fixed, _ = self.ok(
            'psim_plan_edit',
            plan=str(work / 'crowded.json'),
            operations=[{'op': 'place_text', 'all': True}],
            output=str(work / 'fixed.json'),
        )
        self.assertEqual(fixed['layout_check']['errors'], 0)
        checked, _ = self.ok('psim_check', plan=str(work / 'fixed.json'))
        self.assertTrue(checked['summary']['passed'])
        self.assertFalse(codes(checked) & TEXT_CODES)
        after = {e.get('name'): e for e in read(work / 'fixed.json')['elements'] if e.get('name')}
        self.assertEqual(after['R1']['attributes']['Resistance'], '220')
        self.assertNotEqual(after['C1'], elements['C1'])

        _, images = self.ok('psim_render', plan=str(work / 'fixed.json'), target=self.picture(work, 'view'))
        if PNG_BACKEND:
            self.assertTrue(images and images[0].startswith(b'\x89PNG'))

        # 离线预仿真的 CSV 画成曲线并转成 Excel 表；名字带 presim，交付时不会混进 PSIM 结果。
        self.ok('psim_presim', plan=str(work / 'fixed.json'), csv=str(work / 'presim.csv'))
        curves, _ = self.ok(
            'psim_waveforms', csv=str(work / 'presim.csv'), folder=str(work / 'curves'), signals=['Vout']
        )
        self.assertEqual(curves['plotted'], ['Vout'])
        self.assertTrue(Path(curves['xlsx']).name == 'presim-waveforms.xlsx' and Path(curves['xlsx']).is_file())
        self.assertTrue(Path(curves['plot']).is_file())
        self.assertGreater(curves['summary']['Vout']['max'], 0)

        kit, _ = self.ok('psim_package', plan=str(work / 'fixed.json'), folder=str(work / 'kit'))
        self.assertTrue((work / 'kit/build.bat').is_file(), kit)


if __name__ == '__main__':
    unittest.main()
