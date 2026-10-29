"""跨系统工具的可移植检查：文件读写、导入修改、渲染、构建包、交付、MCP 与安装器。"""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout/scripts'
PSIM = ROOT / 'skills/psim-simulation-layout/scripts'
sys.path.insert(0, str(AD))
import native_ad  # noqa: E402
import plan_tools  # noqa: E402
import schdoc  # noqa: E402

AD_PLAN = ROOT / 'skills/ad-schematic-layout/assets/rc-filter-plan.json'
PSIM_PLAN = ROOT / 'skills/psim-simulation-layout/assets/rc-filter-plan.json'
# 示例 SchDoc 的固定哈希：生成器输出在任何系统上都必须逐字节相同；有意修改生成器时同步更新。
EXAMPLE_SHA256 = 'bd8a32b1df5075a3ebedfcc4c89ce5359bd79a0842b54bbfa27505f85180cedc'
SHARED = (
    'canvas.py',
    'capture.py',
    'deliver.py',
    'mcp_server.py',
    'review_emf_text.py',
    'compare_results.py',
    'native_job.py',
    'native_discovery.py',
)
HAS_PILLOW = importlib.util.find_spec('PIL') is not None


def run(script, *args, cwd=None):
    done = subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        cwd=cwd,
        env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        check=False,
    )
    output = done.stdout.decode('utf-8').strip()
    return done.returncode, json.loads(output) if output.startswith(('{', '[')) else output, done.stderr.decode()


class SchDocFiles(unittest.TestCase):
    def test_example_is_byte_identical_and_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            plan = json.loads(AD_PLAN.read_text(encoding='utf-8'))
            first, second = native_ad.create(plan, a), native_ad.create(plan, b)
            self.assertEqual(first['sha256'], second['sha256'])
            self.assertEqual(first['sha256'], EXAMPLE_SHA256)
            project = Path(a, 'RC_Filter.PrjPcb').read_bytes()
            self.assertTrue(project.startswith(b'\xef\xbb\xbf[Design]\r\n'))
            self.assertNotIn(b'\n', project.replace(b'\r\n', b''))

    def test_compound_file_round_trip_with_large_and_small_streams(self):
        streams = {'FileHeader': os.urandom(9000), 'Storage': b'small', 'Additional': b''}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.SchDoc'
            schdoc.write_compound(path, streams)
            self.assertEqual(schdoc.read_compound(path), streams)

    def test_binary_pin_record_is_decoded_and_owned(self):
        component = schdoc.encode({'RECORD': '1', 'LIBREFERENCE': 'X'})

        def pascal(text):
            return bytes([len(text)]) + text.encode()

        body = struct.pack('<IBhBBBBB', 2, 0, 1, 0, 0, 0, 0, 0) + pascal('')
        body += struct.pack('<BBBhhhI', 1, 4, 0x38 | 2, 30, -10, 20, 0) + pascal('VIN') + pascal('7')
        body += pascal('') + pascal('|&|') + pascal('')
        raw = schdoc.encode({'HEADER': 'x'}) + component + struct.pack('<I', len(body) | 1 << 24) + body
        records = schdoc.decode_records(raw)
        pin = records[2]
        self.assertEqual((pin['NAME'], pin['DESIGNATOR'], pin['PINLENGTH']), ('VIN', '7', '30'))
        self.assertEqual((pin['LOCATION.X'], pin['LOCATION.Y'], pin['OWNERINDEX']), ('-10', '20', '0'))
        self.assertEqual(int(pin['PINCONGLOMERATE']) & 3, 2)


class PlanEditing(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        native_ad.create(json.loads(AD_PLAN.read_text(encoding='utf-8')), self.folder)
        self.records = schdoc.read(Path(self.folder) / 'RC_Filter.SchDoc')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_import_rebuilds_identical_records(self):
        plan, unsupported = plan_tools.import_records(self.records, 'RC_Filter')
        self.assertEqual(unsupported, [])
        rebuilt = native_ad.build(plan).records
        self.assertEqual(rebuilt[1:], self.records[1:])

    def test_move_reroutes_wires_orthogonally_and_keeps_topology(self):
        plan, _ = plan_tools.import_records(self.records, 'RC_Filter')
        edited = plan_tools.apply_edits(
            plan, [{'op': 'move', 'ref': 'R1', 'dy': 20}, {'op': 'set_value', 'ref': 'R1', 'value': '4.7k'}]
        )
        from check_layout import check_plan

        result = check_plan(edited)
        self.assertEqual(result['summary']['errors'], 0, result['findings'])
        self.assertTrue(result['topology']['match'])
        self.assertEqual(plan['parts'][1]['value'], '10k')

    def test_rename_updates_references(self):
        plan, _ = plan_tools.import_records(self.records, 'RC_Filter')
        edited = plan_tools.apply_edits(plan, [{'op': 'rename', 'ref': 'R1', 'to': 'R9'}])
        self.assertIn('R9.1', edited['pin_map'])
        self.assertTrue(any('R9.1' in wire for wire in edited['wires']))

    def test_route_respects_pin_axes(self):
        self.assertEqual(plan_tools.route([(0, 0), (40, 20)], ['H', 'H']), [(0, 0), (20, 0), (20, 20), (40, 20)])
        self.assertEqual(plan_tools.route([(0, 0), (40, 20)], ['H', 'V']), [(0, 0), (40, 0), (40, 20)])

    def test_render_writes_svg_and_png(self):
        from render import render_records

        with tempfile.TemporaryDirectory() as folder:
            svg = render_records(self.records, Path(folder) / 'a.svg')
            self.assertIn('<svg', Path(svg['render']).read_text(encoding='utf-8'))
            if HAS_PILLOW:
                png = render_records(self.records, Path(folder) / 'a.png')
                self.assertTrue(Path(png['render']).read_bytes().startswith(b'\x89PNG'))


class PsimCommands(unittest.TestCase):
    def test_plan_edit_avoids_symbols(self):
        operations = json.dumps([{'op': 'move', 'name': 'R1', 'dy': -10}])
        with tempfile.TemporaryDirectory() as folder:
            ops = Path(folder) / 'ops.json'
            ops.write_text(operations, encoding='utf-8')
            code, result, _ = run(PSIM / 'native_psim.py', 'plan-edit', PSIM_PLAN, ops, Path(folder) / 'out.json')
            self.assertEqual(code, 0, result)
            self.assertEqual(result['layout_check']['warnings'], 0, result)

    def test_package_builds_a_runnable_windows_kit(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = Path(folder) / 'kit'
            code, result, error = run(PSIM / 'native_psim.py', 'package', PSIM_PLAN, kit, '--name', 'RC_Filter')
            self.assertEqual(code, 0, error)
            bat = (kit / 'build.bat').read_bytes()
            bat.decode('ascii')
            self.assertNotIn(b'\n', bat.replace(b'\r\n', b''))
            self.assertIn(b'tools\\native_psim.py build . || goto :fail', bat)
            self.assertIn(b'pause', bat)
            self.assertEqual(json.loads((kit / 'kit.json').read_text(encoding='utf-8')), {'name': 'RC_Filter'})
            code, check, error = run(kit / 'tools' / 'native_psim.py', 'check', 'plan.json', cwd=kit)
            self.assertEqual((code, check['summary']['errors']), (0, 0), error)
            code, _, error = run(kit / 'tools' / 'native_psim.py', 'create', 'plan.json', 'x.psimsch', cwd=kit)
            if os.name != 'nt':
                self.assertEqual(code, 1)
                self.assertIn('Windows', error)

    def test_render_svg(self):
        with tempfile.TemporaryDirectory() as folder:
            code, result, error = run(PSIM / 'native_psim.py', 'render', PSIM_PLAN, Path(folder) / 'p.svg')
            self.assertEqual(code, 0, error)
            self.assertIn('stroke="#ff0000"', Path(result['render']).read_text(encoding='utf-8'))


class Delivery(unittest.TestCase):
    FILES = {
        'RC.PrjPcb': 'p',
        'RC.SchDoc': 's',
        'drawing/RC.png': 'i',
        'draft.png': 'd',
        'plan.json': '{}',
        'build-report.json': '{}',
        'build.py': 'x',
        'build.bat': 'b',
        'old.zip': 'z',
        '__pycache__/a.pyc': 'c',
        'sim/result.smv': 'r',
        'sim/native.csv': 'c',
        'sim/waveforms.xlsx': 'x',
        'sim/waveforms.png': 'w',
        'preflight/presim.csv': 'p',
        'model.psimsch': 'm',
    }

    def work(self, root):
        work = Path(root, 'work')
        for name, text in self.FILES.items():
            Path(work, name).parent.mkdir(parents=True, exist_ok=True)
            Path(work, name).write_text(text, encoding='utf-8')
        return work

    def test_customer_folder_holds_only_models_drawings_and_results(self):
        from deliver import deliver

        with tempfile.TemporaryDirectory() as root:
            work = self.work(root)
            result = deliver(work, Path(root, 'out'), 'RC')
            delivered = [
                'RC.PrjPcb',
                'RC.SchDoc',
                'drawing/RC.png',
                'model.psimsch',
                'sim/native.csv',
                'sim/result.smv',
                'sim/waveforms.png',
                'sim/waveforms.xlsx',
            ]
            self.assertEqual(sorted(result['delivered']), delivered)
            customer = Path(root, 'out', 'RC')
            self.assertEqual(
                sorted(p.relative_to(customer).as_posix() for p in customer.rglob('*') if p.is_file()), delivered
            )
            self.assertEqual(sorted(p.name for p in Path(root, 'out').iterdir()), ['RC'])
            self.assertIn('plan.json', result['not_delivered'])
            self.assertEqual(result['sha256']['RC.SchDoc'], hashlib.sha256(b's').hexdigest())
            self.assertTrue(Path(work, 'RC.SchDoc').is_file() and Path(work, 'plan.json').is_file())
            with self.assertRaises(FileExistsError):
                deliver(work, Path(root, 'out'), 'RC')

    def test_include_cannot_deliver_process_files(self):
        from deliver import deliver

        with tempfile.TemporaryDirectory() as root:
            work = self.work(root)
            Path(work, 'params.txt').write_text('R=1', encoding='utf-8')
            result = deliver(work, Path(root, 'out'), 'RC', include=['*.json', 'build.*', 'params*.txt'])
            self.assertIn('params.txt', result['delivered'])
            self.assertFalse({'plan.json', 'build-report.json', 'build.py', 'build.bat'} & set(result['delivered']))
            self.assertTrue(any('build-report.json' in w and 'build.py' in w for w in result['warnings']))

    def test_archive_is_opt_in_and_keeps_a_manifest(self):
        from deliver import deliver

        with tempfile.TemporaryDirectory() as root:
            result = deliver(self.work(root), Path(root, 'out'), 'RC', archive=True)
            archive = Path(result['archive'])
            self.assertEqual(archive, Path(root, 'out', 'RC-archive').resolve())
            self.assertTrue((archive / 'plan.json').is_file() and (archive / 'old.zip').is_file())
            manifest = json.loads((archive / 'manifest.json').read_text(encoding='utf-8'))
            entry = next(f for f in manifest['files'] if f['path'] == 'RC.SchDoc')
            self.assertEqual(entry['sha256'], hashlib.sha256(b's').hexdigest())

    def test_clean_removes_only_regenerable_caches(self):
        from deliver import deliver

        with tempfile.TemporaryDirectory() as root:
            work = self.work(root)
            for name in ('.DS_Store', 'Thumbs.db', 'History/RC.~(1).SchDoc', 'RC.SchDoc.bak', '__Previews/RC.prv'):
                Path(work, name).parent.mkdir(parents=True, exist_ok=True)
                Path(work, name).write_text('x', encoding='utf-8')
            result = deliver(work, Path(root, 'out'), 'RC', clean_cache=True)
            self.assertEqual(sorted(result['cleaned']), ['.DS_Store', 'Thumbs.db', '__Previews/', '__pycache__/'])
            left = sorted(p.relative_to(work).as_posix() for p in work.rglob('*') if p.is_file())
            self.assertEqual(
                left, sorted({*self.FILES, 'History/RC.~(1).SchDoc', 'RC.SchDoc.bak'} - {'__pycache__/a.pyc'})
            )


class McpServer(unittest.TestCase):
    def session(self, *messages):
        data = ''.join(json.dumps(m) + '\n' for m in messages).encode()
        done = subprocess.run(
            [sys.executable, str(AD / 'mcp_server.py'), '--with', str(PSIM)],
            input=data,
            capture_output=True,
            timeout=300,
            cwd=ROOT,
            check=False,
        )
        return {r.get('id'): r for r in map(json.loads, done.stdout.decode().splitlines())}

    def test_protocol(self):
        replies = self.session(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {
                'jsonrpc': '2.0',
                'id': 3,
                'method': 'tools/call',
                'params': {'name': 'ad_check', 'arguments': {'plan': str(AD_PLAN)}},
            },
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'psim_check', 'arguments': {}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'unknown'},
            {
                'jsonrpc': '2.0',
                'id': 6,
                'method': 'tools/call',
                'params': {'name': 'psim_check', 'arguments': {'plan': PSIM_PLAN.read_text(encoding='utf-8')}},
            },
        )
        self.assertEqual(replies[1]['result']['protocolVersion'], '2025-06-18')
        names = {t['name'] for t in replies[2]['result']['tools']}
        self.assertTrue({'ad_check', 'ad_import', 'psim_package', 'psim_measure'} <= names)
        self.assertFalse(replies[3]['result']['isError'])
        self.assertTrue(replies[4]['result']['isError'])
        self.assertEqual(replies[5]['error']['code'], -32601)
        self.assertFalse(replies[6]['result']['isError'])
        self.assertNotIn(None, replies)

    def test_relative_with_paths_from_the_docs_work_from_the_skill_folder(self):
        # commands.md 的写法：在技能目录下运行，--with 相对 scripts 目录写成 ../../另一个技能/scripts。
        for skill, other in ((AD, 'psim-simulation-layout'), (PSIM, 'ad-schematic-layout')):
            with self.subTest(skill=skill.parent.name):
                done = subprocess.run(
                    [sys.executable, 'scripts/mcp_server.py', '--with', f'../../{other}/scripts', '--list'],
                    capture_output=True,
                    cwd=skill.parent,
                    check=False,
                )
                self.assertEqual(done.returncode, 0, done.stderr.decode())
                self.assertEqual(len(json.loads(done.stdout)), 33)
        done = subprocess.run(
            [sys.executable, str(AD / 'mcp_server.py'), '--with', 'no-such-folder', '--list'],
            capture_output=True,
            check=False,
        )
        self.assertEqual(done.returncode, 2)
        self.assertIn('mcp_tools.py', done.stderr.decode('utf-8'))


class Installers(unittest.TestCase):
    def test_python_installer(self):
        with tempfile.TemporaryDirectory() as home:
            foreign = Path(home, '.claude/skills/ad-schematic-layout')
            foreign.mkdir(parents=True)
            code, result, _ = run(ROOT / 'scripts/install_skills.py', '--home', home)
            self.assertEqual(code, 1)
            self.assertEqual(sum(e['passed'] for e in result['entries']), 3)
            shutil.rmtree(foreign)
            self.assertEqual(run(ROOT / 'scripts/install_skills.py', '--home', home)[0], 0)
            self.assertEqual(run(ROOT / 'scripts/install_skills.py', '--home', home, '--check')[0], 0)
            code, result, _ = run(ROOT / 'scripts/install_skills.py', '--home', home, '--uninstall')
            self.assertEqual({e['status'] for e in result['entries']}, {'removed'})

    @unittest.skipIf(shutil.which('node') is None, 'Node 未安装')
    def test_node_installer_matches_python(self):
        with tempfile.TemporaryDirectory() as home:
            done = subprocess.run(
                ['node', str(ROOT / 'bin/cli.mjs'), 'install', '--home', home, '--all'],
                capture_output=True,
                check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            code, _, _ = run(ROOT / 'scripts/install_skills.py', '--home', home, '--all', '--check')
            self.assertEqual(code, 0)

    @unittest.skipIf(shutil.which('node') is None, 'Node 未安装')
    def test_one_command_setup_installs_skills_and_checks_the_machine(self):
        cli = ['node', str(ROOT / 'bin/cli.mjs'), '--home']
        with tempfile.TemporaryDirectory() as home:
            Path(home, '.zcode').mkdir()
            done = subprocess.run([*cli, home, '--json', '--no-pillow'], capture_output=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads(done.stdout)
            self.assertTrue(report['passed'])
            folders = {Path(e['entry']).parent.relative_to(home).as_posix() for e in report['skills']['entries']}
            self.assertEqual(folders, {'.agents/skills', '.claude/skills', '.zcode/skills'})
            self.assertIn('waveforms', report['psim']['portable_commands'])
            self.assertIn(report['pillow']['status'], ('present', 'skipped'))
            for agent in ('universal', 'claude', 'zcode'):
                self.assertEqual(
                    run(ROOT / 'scripts/install_skills.py', '--home', home, '--agent', agent, '--check')[0], 0
                )
            # 再运行一次就是更新；面向新手的输出是中文步骤而不是 JSON。
            done = subprocess.run([*cli, home, '--no-pillow'], capture_output=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn('安装完成', done.stdout.decode('utf-8'))


class ReadmeCommands(unittest.TestCase):
    def test_commands_create_missing_output_folders(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root, 'work')
            preview = ['--preview', work / 'draft.png'] if HAS_PILLOW else []
            code, result, error = run(AD / 'native_ad.py', 'check', AD_PLAN, *preview, cwd=root)
            self.assertEqual(code, 0, error)
            self.assertEqual(result['summary']['errors'], 0)
            code, result, error = run(AD / 'native_ad.py', 'create', AD_PLAN, work / 'ad', cwd=root)
            self.assertEqual(code, 0, error)
            schematic = work / 'ad/RC_Filter.SchDoc'
            code, result, error = run(AD / 'native_ad.py', 'import', schematic, work / 'new/plan.json', cwd=root)
            self.assertEqual(code, 0, error)
            code, result, error = run(PSIM / 'check_layout.py', PSIM_PLAN, '--output', work / 'psim/report.json')
            self.assertEqual(code, 0, error)
            self.assertTrue((work / 'psim/report.json').is_file())
            if HAS_PILLOW:
                self.assertTrue((work / 'draft.png').is_file())


class SharedFiles(unittest.TestCase):
    def test_shared_modules_are_identical(self):
        for name in SHARED:
            self.assertEqual((AD / name).read_bytes(), (PSIM / name).read_bytes(), name)

    def test_png_writer(self):
        from capture import write_png

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.png'
            write_png(path, 2, 1, bytes([255, 0, 0, 0, 0, 255]))
            raw = path.read_bytes()
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', raw[16:24]), (2, 1))
            if HAS_PILLOW:
                from PIL import Image

                with Image.open(path) as image:
                    self.assertEqual(image.getpixel((1, 0)), (0, 0, 255))

    def test_plans_are_not_mutated_by_edits(self):
        plan = json.loads(AD_PLAN.read_text(encoding='utf-8'))
        snapshot = copy.deepcopy(plan)
        plan_tools.apply_edits(plan, [{'op': 'shift_all', 'dx': 10, 'dy': 0}])
        self.assertEqual(plan, snapshot)


if __name__ == '__main__':
    unittest.main(verbosity=2)
