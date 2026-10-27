"""移动端交接的可移植验证；真实 Windows 求解另在原生环境复验。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
