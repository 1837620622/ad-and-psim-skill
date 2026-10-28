"""Mac/Linux 与 Windows 交接的可移植验证；真实 Windows 求解另在原生环境复验。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
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

        def create(psim, plan, target, overwrite=False):
            self.calls.append('create')
            Path(target).write_bytes(b'native')

        def simulate(psim, source, folder, parameters):
            self.calls.append('simulate')
            folder = Path(folder)
            self.assertFalse((folder / 'result.smv').exists(), '旧结果应在求解前清掉')
            folder.mkdir(exist_ok=True)
            (folder / 'result.smv').write_bytes(b'smv')
            (folder / 'native.csv').write_text('Time\n0\n', encoding='utf-8')
            return {'graph': str(folder / 'result.smv')}

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

    def test_kit_batch_file_is_ascii_and_pauses_on_failure(self):
        bat = self.psim.BUILD_BAT
        bat.encode('ascii')
        self.assertIn('build . || goto :fail', bat)
        self.assertIn('sys.version_info < (3, 10)', bat)
        self.assertIn('if not defined PSIM_NO_PAUSE pause', bat)
        self.assertIn('goto :stop', bat.split('\n:nopython\n', 1)[1].split('\n:fail\n', 1)[0])


if __name__ == '__main__':
    unittest.main()
