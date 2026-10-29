"""Mac/Linux 与 Windows 交接的可移植验证；真实 Windows 求解另在原生环境复验。"""

import csv
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout/scripts'
PSIM = ROOT / 'skills/psim-simulation-layout/scripts'
sys.path.insert(0, str(AD))
from capture import write_png
import native_job


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def fixture(folder):
    job, returned, received = Path(folder, 'job'), Path(folder, 'returned'), Path(folder, 'received')
    write_json(job / 'input/plan.json', {'fixture': True})
    request = {
        'schema_version': 1,
        'tool': 'ad',
        'name': 'Fixture',
        'plan_sha256': native_job.digest(job / 'input/plan.json'),
        'files': native_job.inventory(job),
    }
    write_json(job / native_job.REQUEST, request)
    write_png(returned / 'drawing/Fixture.png', 2, 1, bytes([255, 0, 0, 0, 0, 255]))
    report = {
        'schema_version': 1,
        'tool': 'ad',
        'passed': True,
        'request_sha256': native_job.digest(job / native_job.REQUEST),
        'plan_sha256': request['plan_sha256'],
        'native_preview': {
            'path': 'drawing/Fixture.png',
            'source': 'native_export',
            'sha256': native_job.digest(returned / 'drawing/Fixture.png'),
        },
        'files': native_job.inventory(returned),
    }
    write_json(returned / native_job.RESULT, report)
    return job, returned, received, report


class PortablePreparation(unittest.TestCase):
    def test_both_skills_prepare_self_contained_jobs(self):
        for script in (AD / 'native_ad.py', PSIM / 'native_psim.py'):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as folder:
                job = Path(folder, 'job')
                plan = script.parent.parent / 'assets/rc-filter-plan.json'
                done = subprocess.run(
                    [sys.executable, str(script), 'handoff', str(plan), str(job)], capture_output=True, check=False
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                result = json.loads(done.stdout)
                self.assertFalse(result['native_verified'])
                self.assertEqual(result['preview_source'], 'portable_render')
                self.assertFalse((job / 'native-results').exists())
                request = native_job.read_json(job / native_job.REQUEST)
                native_job.verify_files(job, request['files'])
                self.assertNotIn('references/images', '\n'.join(request['files']))
                copied = job / 'tool/scripts' / script.name
                checked = subprocess.run(
                    [sys.executable, str(copied), 'check', str(job / 'input/plan.json')],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_explicit_dependencies_are_copied_with_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = ROOT / 'skills/ad-schematic-layout/assets/rc-filter-plan.json'
            (folder / 'plan.json').write_bytes(source.read_bytes())
            (folder / 'params.txt').write_text('R=100\n', encoding='utf-8')
            native_job.prepare('ad', folder / 'plan.json', folder / 'job', include=['params.txt'])
            request = native_job.read_json(folder / 'job' / native_job.REQUEST)
            self.assertIn('input/params.txt', request['files'])

    def test_dependency_outside_plan_folder_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'plans').mkdir()
            (folder / 'plans/plan.json').write_bytes(
                (ROOT / 'skills/ad-schematic-layout/assets/rc-filter-plan.json').read_bytes()
            )
            (folder / 'secret.txt').write_text('x', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '计划所在目录'):
                native_job.prepare('ad', folder / 'plans/plan.json', folder / 'job', include=['../secret.txt'])
            self.assertFalse((folder / 'job').exists())

    def test_failed_preparation_leaves_folder_reusable(self):
        plan = ROOT / 'skills/ad-schematic-layout/assets/rc-filter-plan.json'
        real = native_job.command

        def broken(script, arguments, **options):
            if arguments and arguments[0] == 'render':
                return {'exit_code': 1, 'result': None, 'stderr': 'render failed'}
            return real(script, arguments, **options)

        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory, 'job')
            with mock.patch.object(native_job, 'command', broken), self.assertRaises(RuntimeError):
                native_job.prepare('ad', plan, job)
            self.assertFalse(job.exists())
            job.mkdir()
            with mock.patch.object(native_job, 'command', broken), self.assertRaises(RuntimeError):
                native_job.prepare('ad', plan, job)
            self.assertEqual(list(job.iterdir()), [])
            native_job.prepare('ad', plan, job)
            self.assertTrue((job / native_job.REQUEST).is_file())


class ReturnedResults(unittest.TestCase):
    def test_receive_copies_native_pixels_without_rerendering(self):
        with tempfile.TemporaryDirectory() as folder:
            job, returned, received, _ = fixture(folder)
            result = native_job.receive(job, returned, received)
            self.assertTrue(result['native_verified'])
            self.assertTrue(result['preview_bytes_identical'])
            self.assertEqual(Path(result['png']).read_bytes(), (returned / 'drawing/Fixture.png').read_bytes())

    def test_tampered_image_is_rejected_before_writing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            job, returned, received, _ = fixture(folder)
            (returned / 'drawing/Fixture.png').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                native_job.receive(job, returned, received)
            self.assertFalse(received.exists())

    def test_wrong_request_and_failed_native_job_are_rejected(self):
        for changes in ({'request_sha256': 'different'}, {'passed': False}, {'plan_sha256': 'different'}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as folder:
                job, returned, received, report = fixture(folder)
                write_json(returned / native_job.RESULT, dict(report, **changes))
                with self.assertRaises(ValueError):
                    native_job.receive(job, returned, received)
                self.assertFalse(received.exists())

    def test_manifest_paths_cannot_escape_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('../outside', '/absolute', 'C:/outside', '..\\outside'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    native_job.safe_file(folder, name)

    def test_modified_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            job, returned, received, _ = fixture(folder)
            write_json(job / 'input/plan.json', {'changed': True})
            with self.assertRaises(ValueError):
                native_job.receive(job, returned, received)
            self.assertFalse(received.exists())

    def test_destination_inside_job_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            job, returned, _, _ = fixture(folder)
            with self.assertRaises(ValueError):
                native_job.receive(job, returned, job / 'received')


class RuntimeBoundary(unittest.TestCase):
    def test_platform_boundary_is_explicit(self):
        if sys.platform == 'win32':
            self.skipTest('边界在非 Windows CI 中验证')
        with self.assertRaisesRegex(RuntimeError, 'Windows'):
            native_job.run('unused')

    def test_all_shared_job_helpers_are_identical(self):
        for filename in ('native_job.py', 'native_discovery.py', 'compare_results.py'):
            self.assertEqual((AD / filename).read_bytes(), (PSIM / filename).read_bytes())


class Rerun(unittest.TestCase):
    """Windows 上第一次失败后，改好原因直接再双击就能跑，不用手动清目录。"""

    def test_failed_attempt_is_kept_and_rerun_starts_clean(self):
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder, 'native-results')
            write_json(results / native_job.RESULT, {'passed': False, 'error': 'PSIM not found'})
            self.assertEqual(native_job.empty_folder(native_job._set_aside_failed(results)), results.resolve())
            self.assertEqual(list(results.iterdir()), [])
            self.assertTrue(Path(folder, 'native-results.failed-1', native_job.RESULT).is_file())
            (results / 'partial.txt').write_text('stopped halfway', encoding='utf-8')
            native_job._set_aside_failed(results)
            self.assertTrue(Path(folder, 'native-results.failed-2', 'partial.txt').is_file())

    def test_passed_result_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder, 'native-results')
            write_json(results / native_job.RESULT, {'passed': True})
            with self.assertRaises(FileExistsError):
                native_job.empty_folder(native_job._set_aside_failed(results))
            self.assertTrue((results / native_job.RESULT).is_file())

    def test_run_bat_is_ascii_and_waits_on_failure(self):
        bat = native_job.RUN_BAT
        bat.encode('ascii')
        self.assertIn('sys.version_info < (3, 11)', bat)
        self.assertIn('|| goto :fail', bat)
        self.assertIn('pause', bat)
        # 没找到 Python 时还没有结果文件，不应再提示去看它。
        self.assertIn('goto :stop', bat.split('\n:nopython\n', 1)[1].split('\n:fail\n', 1)[0])

    def test_missing_pillow_stops_before_the_vendor_software_starts(self):
        with (
            mock.patch.object(native_job.os, 'name', 'nt'),
            mock.patch.object(native_job.importlib.util, 'find_spec', return_value=None),
            self.assertRaisesRegex(RuntimeError, 'Pillow'),
        ):
            native_job.run('unused')


def load_native_psim():
    """单独加载 PSIM 的 native_psim（与 AD 脚本同名模块不冲突）。"""
    spec = importlib.util.spec_from_file_location('kit_native_psim', PSIM / 'native_psim.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsKit(unittest.TestCase):
    """build.bat 调用的 build 命令：步骤顺序、重复运行与失败报告（PSIM 接口用替身）。"""

    def setUp(self):
        self.psim = load_native_psim()
        self.calls = []
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.folder, ignore_errors=True))
        write_json(self.folder / 'plan.json', {'elements': []})
        write_json(self.folder / 'kit.json', {'name': '测试电路'})
        self.review = {'passed': True}
        self.references, self.reference_passes = [], True

        def create(psim, plan, target, overwrite=False):
            self.calls.append('create')
            Path(target).write_bytes(b'native')

        def simulate(psim, source, folder, parameters, reference=None):
            self.calls.append('simulate')
            self.references.append(reference)
            folder = Path(folder)
            self.assertFalse((folder / 'result.smv').exists(), '旧结果应在求解前清掉')
            self.assertFalse((folder / 'waveforms.xlsx').exists(), '旧曲线和表格应在求解前清掉')
            folder.mkdir(exist_ok=True)
            (folder / 'result.smv').write_bytes(b'smv')
            (folder / 'native.csv').write_text('Time\n0\n', encoding='utf-8')
            (folder / 'waveforms.xlsx').write_bytes(b'xlsx')
            result = {'graph': str(folder / 'result.smv')}
            if reference is not None:
                result['reference'] = {'passed': self.reference_passes}
            return result

        def export(psim, source, target):
            self.calls.append('export')
            Path(target).parent.mkdir(exist_ok=True)
            Path(target).write_bytes(b'emf')
            return {'emf': str(target), 'text_review': self.review}

        def open_model(source, psim_dir=None):
            self.calls.append('open')
            return {'opened': str(source)}

        for name, stub in (('create', create), ('simulate', simulate), ('export', export), ('open_model', open_model)):
            patcher = mock.patch.object(self.psim, name, stub)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.psim, 'precheck', lambda plan: {'summary': {'errors': 0, 'warnings': 0}})
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, **options):
        with mock.patch('sys.stderr', new=__import__('io').StringIO()):
            return self.psim.build(self.folder, psim=object(), open_after=True, **options)

    def test_build_runs_every_step_and_opens_the_model(self):
        report = self.build()
        self.assertEqual(self.calls, ['create', 'simulate', 'export', 'open'])
        self.assertTrue(report['passed'])
        self.assertTrue((self.folder / '测试电路.psimsch').is_file())
        saved = json.loads((self.folder / 'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['steps']['create']['status'], 'created')

    def test_second_run_keeps_the_model_and_redoes_outputs(self):
        self.build()
        (self.folder / '测试电路.psimsch').write_bytes(b'edited in PSIM')
        self.calls.clear()
        report = self.build()
        self.assertEqual(self.calls, ['simulate', 'export', 'open'])
        self.assertEqual(report['steps']['create']['status'], 'reused')
        self.assertEqual((self.folder / '测试电路.psimsch').read_bytes(), b'edited in PSIM')

    def test_failure_is_reported_and_the_model_still_opens(self):
        def broken(*args):
            raise RuntimeError('solver stopped')

        with mock.patch.object(self.psim, 'simulate', broken), self.assertRaisesRegex(RuntimeError, 'solver'):
            self.build()
        saved = json.loads((self.folder / 'build-report.json').read_text(encoding='utf-8'))
        self.assertIn('solver stopped', saved['error'])
        self.assertFalse(saved['passed'])
        self.assertEqual(self.calls, ['create', 'open'])

    def test_failed_text_review_marks_the_build_failed(self):
        self.review = {'passed': False}
        report = self.build()
        self.assertFalse(report['passed'])
        self.assertIn('text_review', report['note'])

    def test_kit_reference_is_compared_and_a_mismatch_fails_the_build(self):
        original = self.folder / 'reference/原始模型.psimsch'
        original.parent.mkdir()
        original.write_bytes(b'original')
        write_json(self.folder / 'kit.json', {'name': '测试电路', 'reference': 'reference/原始模型.psimsch'})
        self.assertTrue(self.build()['passed'])
        self.assertEqual(self.references, [original.resolve()])
        self.reference_passes = False
        report = self.build()
        self.assertFalse(report['passed'])
        self.assertIn('原始文件不一致', report['note'])
        for bad in ('../plan.json', 'reference/../kit.json', 'reference/missing.psimsch'):
            write_json(self.folder / 'kit.json', {'name': '测试电路', 'reference': bad})
            with self.subTest(reference=bad), self.assertRaises(ValueError):
                self.build()

    def test_kit_batch_file_is_ascii_and_pauses_on_failure(self):
        bat = self.psim.BUILD_BAT
        bat.encode('ascii')
        self.assertIn('build . || goto :fail', bat)
        self.assertIn('sys.version_info < (3, 10)', bat)
        self.assertIn('if not defined PSIM_NO_PAUSE pause', bat)
        self.assertIn('goto :stop', bat.split('\n:nopython\n', 1)[1].split('\n:fail\n', 1)[0])


class Curve:
    def __init__(self, name, values):
        self.Name, self.Values, self.Rows = name, values, len(values)


class FakePsim:
    """PSIM 接口替身：波形由模型文件里写的增益决定，同样的模型和参数给出同样的波形。"""

    def __init__(self):
        self.calls = []

    def PsimSimulate(self, source, graph, **parameters):  # noqa: N802 - PSIM 接口的名字
        self.calls.append((Path(source).name, Path(graph), parameters))
        Path(graph).write_bytes(b'smv')
        gain = float(Path(source).read_text(encoding='utf-8'))
        samples = [i * 1e-6 for i in range(100)]
        curves = [Curve('Time', samples), Curve('Vout', [gain * (1 - math.exp(-t / 2e-5)) for t in samples])]
        return type('Result', (), {'Result': 1, 'Graph': curves})()

    def get_psim_version(self):
        return (2025, 1)


class NativeSimulate(unittest.TestCase):
    """simulate 写出 SMV、CSV、曲线和逐格相同的 XLSX；给了原始文件时逐点对照（PSIM 接口用替身）。"""

    def setUp(self):
        self.psim = load_native_psim()
        self.folder = Path(tempfile.mkdtemp()).resolve()  # macOS 的 /var 是 /private/var 的链接
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.model = self.original('model.psimsch', '10')
        # 实际运行时 native_psim.py 作为脚本启动，同目录的 waveforms.py 在 sys.path 上。
        patcher = mock.patch.object(sys, 'path', [str(PSIM), *sys.path])
        patcher.start()
        self.addCleanup(patcher.stop)

    def original(self, name, text):
        path = self.folder / name
        path.write_text(text, encoding='utf-8')
        return path

    def simulate(self, folder, reference=None, parameters=None, api=None):
        return self.psim.simulate(api or FakePsim(), self.model, self.folder / folder, parameters or {}, reference)

    def test_simulate_writes_curves_and_workbook_next_to_the_csv(self):
        result = self.simulate('result')
        curves = result['waveforms']
        self.assertEqual(curves['status'], 'written', curves)
        self.assertEqual(Path(curves['xlsx']), self.folder / 'result/waveforms.xlsx')
        self.assertTrue(curves['xlsx_check']['identical'])
        self.assertEqual(curves['xlsx_check']['data_rows'], 100)
        self.assertTrue(Path(curves['plot']).is_file())
        self.assertAlmostEqual(curves['summary']['Vout']['max'], result_max(self.folder / 'result/native.csv'))
        self.assertNotIn('reference', result)

    def test_original_model_is_solved_again_with_the_same_parameters(self):
        api = FakePsim()
        check = self.simulate('result', self.original('原始.psimsch', '10'), {'TotalTime': 1e-4}, api)['reference']
        self.assertTrue(check['passed'], check)
        self.assertEqual(check['equivalence'], 'byte_identical')
        self.assertEqual(check['method'], 'same parameters, re-solved')
        self.assertEqual(check['reference'], str(self.folder / '原始.psimsch'))
        (_, _, mine), (name, graph, theirs) = api.calls
        self.assertEqual((name, theirs), ('原始.psimsch', mine))
        self.assertFalse(graph.parent.exists(), '对照用的临时求解结果应删掉')
        changed = self.simulate('again', self.original('改过.psimsch', '10.001'))['reference']
        self.assertFalse(changed['passed'])
        self.assertEqual(changed['equivalence'], 'different')
        self.assertEqual(changed['first_mismatches'][0]['signal'], 'Vout')

    def test_original_csv_is_compared_as_given(self):
        first = self.simulate('first')
        exact = self.folder / 'native-original.csv'
        shutil.copy(first['csv'], exact)
        self.assertEqual(self.simulate('second', exact)['reference']['equivalence'], 'byte_identical')
        # SIMVIEW 式的定位数导出：每个数都写 8 位有效数字，逐位相同算一致，差一位就不一致。
        with open(first['csv'], newline='', encoding='utf-8-sig') as stream:
            header, *rows = list(csv.reader(stream))
        lines = [','.join(header), *(','.join(f'{float(v):.7E}' for v in row) for row in rows)]
        printed = self.folder / 'simview.csv'
        printed.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        check = self.simulate('third', printed)['reference']
        self.assertTrue(check['passed'], check)
        self.assertEqual(check['equivalence'], 'printed_digits_equal')
        self.assertEqual(check['reference_significant_digits'], 8)
        lines[50] = f'{float(rows[49][0]):.7E},{float(rows[49][1]) * 1.000001:.7E}'
        printed.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        check = self.simulate('fourth', printed)['reference']
        self.assertFalse(check['passed'])
        self.assertEqual(check['first_mismatches'][0]['sample'], 50)

    def test_a_reference_with_other_columns_fails_with_the_reason(self):
        check = self.simulate('result', self.original('other.csv', 'Time,Iout\n0,1\n1e-6,2\n'))['reference']
        self.assertFalse(check['passed'])
        self.assertIn('列集合', check['reason'])

    def test_bad_reference_is_rejected_before_solving(self):
        api = FakePsim()
        for reference in (self.folder / 'missing.psimsch', self.original('notes.txt', 'x')):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.simulate('result', reference, api=api)
        self.assertEqual(api.calls, [])


class ReferenceHandoff(unittest.TestCase):
    """原始文件随构建包或 Windows 任务带过去，只用来对照，不进 input/、不进交付目录。"""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.plan = PSIM.parent / 'assets/rc-filter-plan.json'
        self.original = self.folder / '原始模型.psimsch'
        self.original.write_bytes(b'original')

    def cli(self, *arguments):
        done = subprocess.run(
            [sys.executable, str(PSIM / 'native_psim.py'), *map(str, arguments)], capture_output=True, check=False
        )
        self.assertEqual(done.returncode, 0, done.stderr.decode('utf-8', errors='replace'))
        return json.loads(done.stdout)

    def test_package_carries_the_original_file_and_delivery_leaves_it_out(self):
        from deliver import classify

        made = self.cli('package', self.plan, self.folder / 'kit', '--name', 'RC', '--reference', self.original)
        self.assertEqual(made['reference'], 'reference/原始模型.psimsch')
        kit = json.loads((self.folder / 'kit/kit.json').read_text(encoding='utf-8'))
        self.assertEqual(kit, {'name': 'RC', 'reference': 'reference/原始模型.psimsch'})
        self.assertEqual((self.folder / 'kit/reference/原始模型.psimsch').read_bytes(), b'original')
        self.assertEqual(classify(Path('reference/原始模型.psimsch')), 'archive')

    def test_windows_job_passes_the_reference_to_simulate_and_fails_on_a_mismatch(self):
        self.cli('handoff', self.plan, self.folder / 'job', '--name', 'RC', '--reference', self.original)
        job = self.folder / 'job'
        request = native_job.read_json(job / native_job.REQUEST)
        self.assertEqual(request['reference'], 'reference/原始模型.psimsch')
        self.assertIn('reference/原始模型.psimsch', request['files'])
        self.assertFalse(any(name.startswith('input/') and '原始' in name for name in request['files']))
        seen, passes = [], [False]

        def command(script, arguments, **options):
            seen.append([str(a) for a in arguments])
            result = {'native_available': True}
            if arguments[0] == 'simulate':
                result = {'csv': 'missing.csv', 'columns': [], 'reference': {'passed': passes[0]}}
            elif arguments[0] == 'export':
                write_png(Path(arguments[2]).with_suffix('.png'), 1, 1, bytes(3))
                result = {'text_review': {'passed': True}, 'png': str(Path(arguments[2]).with_suffix('.png'))}
            return {'exit_code': 0 if result.get('reference', {}).get('passed', True) else 1, 'result': result}

        windows = SimpleNamespace(name='nt', environ=os.environ)  # 只替换 run 看到的 os，pathlib 不受影响
        with (
            mock.patch.object(native_job, 'os', windows),
            mock.patch.object(native_job.importlib.util, 'find_spec', lambda name: object()),
            mock.patch.object(native_job, 'command', command),
        ):
            report = native_job.run(job)
            self.assertFalse(report['passed'])
            self.assertIn('原始文件不一致', report['error'])
            self.assertEqual(report['reference'], {'passed': False})
            passes[0] = True
            report = native_job.run(job)
        self.assertTrue(report['passed'], report.get('error'))
        simulate = next(a for a in seen if a[0] == 'simulate')
        self.assertEqual(simulate[-2:], ['--reference', str(job / 'reference/原始模型.psimsch')])
        self.assertEqual(report['reference'], {'passed': True})
        self.assertFalse(any('原始' in name for name in report['files']), '原始文件不随结果返回')
        self.assertTrue((job / 'native-results.failed-1').is_dir())
        received = native_job.receive(job, job / 'native-results', self.folder / 'final')
        self.assertEqual(received['reference'], {'passed': True})
        manifest = job / 'native-results' / native_job.RESULT
        native_job.write_json(manifest, dict(report, reference=None))  # 对照结果被去掉的返回清单不能接收
        with self.assertRaisesRegex(ValueError, '原始文件对照'):
            native_job.receive(job, job / 'native-results', self.folder / 'final-2')

    def test_only_psim_jobs_take_a_reference(self):
        with self.assertRaisesRegex(ValueError, 'PSIM'):
            native_job.prepare(
                'ad', AD.parent / 'assets/rc-filter-plan.json', self.folder / 'job', reference=self.original
            )
        self.assertFalse((self.folder / 'job').exists())


def result_max(path):
    lines = Path(path).read_text(encoding='utf-8-sig').splitlines()[1:]
    return max(float(line.split(',')[1]) for line in lines)


if __name__ == '__main__':
    unittest.main()
