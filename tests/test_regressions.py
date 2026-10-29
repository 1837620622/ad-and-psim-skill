"""覆盖审计中实际复现的源文件保护、拓扑、质量闸门和分发问题。"""

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout/scripts'
PSIM = ROOT / 'skills/psim-simulation-layout/scripts'
sys.path.insert(0, str(AD))
import native_ad
import plan_tools
import schdoc
from deliver import deliver
from mcp_server import Server
from compare_results import compare_files, compare_waveforms


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


psim_plan = load(PSIM / 'psim_plan.py', 'regression_psim_plan')
native_psim = load(PSIM / 'native_psim.py', 'regression_native_psim')
AD_PLAN = json.loads((AD.parent / 'assets/rc-filter-plan.json').read_text(encoding='utf-8'))
PSIM_PLAN = json.loads((PSIM.parent / 'assets/rc-filter-plan.json').read_text(encoding='utf-8'))


class SourceProtection(unittest.TestCase):
    def test_report_never_overwrites_an_existing_file(self):
        for script in (AD / 'native_ad.py', PSIM / 'native_psim.py'):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as folder:
                report = Path(folder, 'report.json')
                original = b'{"keep":"original"}'
                report.write_bytes(original)
                done = subprocess.run(
                    [sys.executable, str(script), '--report', str(report), 'env'], capture_output=True, check=False
                )
                self.assertNotEqual(done.returncode, 0)
                self.assertEqual(report.read_bytes(), original)

    def test_report_cannot_replace_a_generated_plan_or_layout_check(self):
        for script, command, generated in (
            (AD / 'native_ad.py', 'create', 'layout-check.json'),
            (PSIM / 'native_psim.py', 'package', 'plan.json'),
        ):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as folder:
                target = Path(folder, 'output')
                report = target / generated
                plan = script.parent.parent / 'assets/rc-filter-plan.json'
                done = subprocess.run(
                    [sys.executable, str(script), '--report', str(report), command, str(plan), str(target)],
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(done.returncode, 0)
                data = json.loads(report.read_text(encoding='utf-8'))
                if command == 'create':
                    self.assertIn('summary', data)
                    self.assertNotIn('project', data)
                else:
                    self.assertEqual(data, PSIM_PLAN)

    def test_gbk_text_is_not_misread_as_valid_utf8(self):
        record = {'RECORD': '4', 'TEXT': '漏'}
        self.assertEqual(schdoc.decode_records(schdoc.encode(record)), [record])
        utf8 = b'|RECORD=4|%UTF8%TEXT=' + '漏'.encode() + b'\x00'
        self.assertEqual(schdoc.decode_records(struct.pack('<I', len(utf8)) + utf8), [record])

    def test_import_cannot_replace_original_schdoc_with_json(self):
        with tempfile.TemporaryDirectory() as folder:
            native_ad.create(AD_PLAN, folder)
            source = Path(folder, 'RC_Filter.SchDoc')
            original = source.read_bytes()
            done = subprocess.run(
                [sys.executable, str(AD / 'native_ad.py'), 'import', str(source), str(source)],
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(done.returncode, 0)
            self.assertEqual(source.read_bytes(), original)

    def test_import_preserves_additional_component_parameters(self):
        sheet = native_ad.build(AD_PLAN)
        owner = next(r['OWNERINDEX'] for r in sheet.records if r.get('RECORD') == '34' and r.get('TEXT') == 'R1')
        sheet.add(41, OWNERINDEX=owner, OWNERPARTID=-1, NAME='Tolerance', TEXT='1%', ISHIDDEN='T', FONTID=1)
        imported, unsupported = plan_tools.import_records(sheet.records)
        self.assertFalse(unsupported)
        rebuilt = native_ad.build(imported).records
        self.assertTrue(any(r.get('NAME') == 'Tolerance' and r.get('TEXT') == '1%' for r in rebuilt))

    def test_unrepresentable_model_data_is_reported(self):
        sheet = native_ad.build(AD_PLAN)
        owner = next(r['OWNERINDEX'] for r in sheet.records if r.get('RECORD') == '34' and r.get('TEXT') == 'R1')
        sheet.add(44, OWNERINDEX=owner)
        _, unsupported = plan_tools.import_records(sheet.records)
        self.assertTrue(any(r.get('ref') == 'R1' for r in unsupported))

    def test_electrical_types_outside_named_subset_are_preserved(self):
        sheet = native_ad.build(AD_PLAN)
        pin = next(r for r in sheet.records if r.get('RECORD') == '2')
        pin['ELECTRICAL'] = '5'
        imported, unsupported = plan_tools.import_records(sheet.records)
        self.assertFalse(unsupported)
        rebuilt = native_ad.build(imported).records
        self.assertEqual(next(r['ELECTRICAL'] for r in rebuilt if r.get('RECORD') == '2'), '5')


class TopologyProtection(unittest.TestCase):
    def test_move_retains_shared_probe_node(self):
        expected = psim_plan.port_nets(PSIM_PLAN)
        changed = psim_plan.apply_edits(PSIM_PLAN, [{'op': 'move', 'name': 'C1', 'dx': -50, 'dy': 40}])
        self.assertEqual(psim_plan.port_nets(changed), expected)
        self.assertEqual(
            next(e for e in changed['elements'] if e.get('name') == 'Vout')['attributes']['PORTS'], '{250,100}'
        )

    def test_moving_probe_keeps_circuit_node_connected(self):
        changed = psim_plan.apply_edits(PSIM_PLAN, [{'op': 'move', 'name': 'Vout', 'dx': -50, 'dy': -30}])
        self.assertEqual(psim_plan.port_nets(changed), psim_plan.port_nets(PSIM_PLAN))


class SoftwareLocation(unittest.TestCase):
    def test_quoted_environment_paths_are_accepted(self):
        # 资源管理器“复制文件地址”得到带引号的路径，直接粘进环境变量也要能找到软件。
        with tempfile.TemporaryDirectory() as folder:
            psim = Path(folder, 'PSIM 2026')
            (psim / 'Python/Samples').mkdir(parents=True)
            (psim / 'PSIM2.dll').write_bytes(b'')
            (psim / 'Python/Samples/Psim_Class.py').write_text('', encoding='utf-8')
            ad = Path(folder, 'X2.EXE')
            ad.write_bytes(b'')
            with patch.dict(os.environ, {'PSIM_DIR': f' "{psim}" ', 'AD_EXE': f'"{ad}"'}):
                self.assertEqual(native_psim.find_psim(), psim)
                self.assertEqual(native_ad.find_ad(), ad)


class ResultComparison(unittest.TestCase):
    def files(self, folder, candidate):
        reference, target = Path(folder, 'reference.csv'), Path(folder, 'candidate.csv')
        reference.write_text('Time,Vout\n0,0\n1,1\n', encoding='utf-8')
        target.write_text(candidate, encoding='utf-8')
        return reference, target

    def test_different_serialization_is_numeric_equality_not_byte_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, target = self.files(folder, 'Time,Vout\n0.0,0.0\n1.0,1.0\n')
            self.assertFalse(compare_files(reference, target)['passed'])
            self.assertEqual(compare_waveforms(reference, target)['equivalence'], 'numeric_equal')

    def test_tolerance_agreement_is_not_called_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, target = self.files(folder, 'Time,Vout\n0,0\n1,1.00001\n')
            self.assertFalse(compare_waveforms(reference, target)['passed'])
            self.assertEqual(compare_waveforms(reference, target, atol=0.0001)['equivalence'], 'within_tolerance')

    def test_fixed_digit_reference_is_matched_digit_for_digit_only(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, target = self.files(folder, 'Time,Vout\n0,0.123456789\n1,1\n')
            reference.write_text(
                'Time,Vout\n0.0000000E+000,1.2345679E-001\n1.0000000E+000,1.0000000E+000\n', encoding='utf-8'
            )
            check = compare_waveforms(reference, target)
            self.assertEqual((check['equivalence'], check['reference_significant_digits']), ('printed_digits_equal', 8))
            target.write_text('Time,Vout\n0,0.12345674\n1,1\n', encoding='utf-8')
            self.assertFalse(compare_waveforms(reference, target)['passed'])
            # 位数不统一（如最短往返写法）时不按位数放宽：0.1 和 0.10000000000000003 是不同的数。
            reference.write_text('Time,Vout\n0,0.1\n1,1.5e-3\n', encoding='utf-8')
            target.write_text('Time,Vout\n0,0.10000000000000003\n1,1.5e-3\n', encoding='utf-8')
            self.assertEqual(compare_waveforms(reference, target)['equivalence'], 'different')

    def test_grid_difference_is_not_hidden_with_interpolation(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, target = self.files(folder, 'Time,Vout\n0,0\n1.1,1\n')
            self.assertFalse(compare_waveforms(reference, target)['passed'])

    def test_extra_samples_and_invalid_data_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, target = self.files(folder, 'Time,Vout\n0,0\n1,1\n2,2\n')
            self.assertFalse(compare_waveforms(reference, target)['passed'])
            for content in ('Time,Vout\n0,0\n0,1\n', 'Time,Vout\n0,0\n1,nan\n'):
                target.write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    compare_waveforms(reference, target)

    def test_complete_comparison_requires_all_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, target = self.files(folder, 'Time,Vout,Extra\n0,0,0\n1,1,0\n')
            with self.assertRaises(ValueError):
                compare_waveforms(reference, target)
            self.assertFalse(compare_waveforms(reference, target, signals=['Vout'])['complete_column_set'])


class ExportGates(unittest.TestCase):
    def test_both_clis_fail_when_native_text_review_fails(self):
        for module, args, prerequisite in (
            (native_ad, ['export', 'model.SchDoc', 'drawing'], 'require_ad'),
            (native_psim, ['export', 'model.psimsch', 'drawing.emf'], 'initialize'),
        ):
            with (
                self.subTest(module=module.__name__),
                patch.object(sys, 'argv', ['tool', *args]),
                patch.object(module, prerequisite),
                patch.object(module, 'export', return_value={'text_review': {'passed': False}}),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(module.main(), 1)


class McpRobustness(unittest.TestCase):
    def test_invalid_shape_does_not_end_session(self):
        server = Server([AD])
        writer = io.BytesIO()
        server.serve(io.BytesIO(b'null\n0\n{"jsonrpc":"2.0","id":3,"method":"ping"}\n'), writer)
        replies = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual([r['error']['code'] for r in replies[:2]], [-32600, -32600])
        self.assertEqual(replies[-1], {'jsonrpc': '2.0', 'id': 3, 'result': {}})


class DeliveryProtection(unittest.TestCase):
    def test_existing_manifest_is_preserved_in_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder, 'work')
            work.mkdir()
            (work / 'X.SchDoc').write_bytes(b'fixture')
            original = '{"source":"keep"}'
            (work / 'manifest.json').write_text(original, encoding='utf-8')
            (work / 'manifest.source.json').write_text('another source file', encoding='utf-8')
            result = deliver(work, Path(folder, 'out'), 'X', archive=True)
            archive = Path(result['archive'])
            manifest = json.loads((archive / 'manifest.json').read_text(encoding='utf-8'))
            copied = next(e for e in manifest['files'] if e.get('source_path') == 'manifest.json')
            self.assertEqual((archive / copied['path']).read_text(encoding='utf-8'), original)
            self.assertEqual((archive / 'manifest.source.json').read_text(encoding='utf-8'), 'another source file')

    def test_name_cannot_escape_output_or_write_back_into_source(self):
        with tempfile.TemporaryDirectory() as folder:
            work, output = Path(folder, 'work'), Path(folder, 'out')
            work.mkdir()
            (work / 'model.SchDoc').write_bytes(b'fixture')
            for name in ('../work/escaped', str(work / 'escaped'), '..', 'folder/name'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    deliver(work, output, name)
            self.assertEqual(sorted(p.name for p in work.iterdir()), ['model.SchDoc'])


class InstallerIntegrity(unittest.TestCase):
    def test_package_accepts_chinese_names(self):
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run(
                [
                    sys.executable,
                    str(PSIM / 'native_psim.py'),
                    'package',
                    str(PSIM.parent / 'assets/rc-filter-plan.json'),
                    str(Path(folder, 'kit')),
                    '--name',
                    '测试电路',
                ],
                capture_output=True,
                check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            # 中文名不进批处理（纯 ASCII，避免代码页问题），由 kit.json 交给 Python。
            Path(folder, 'kit/build.bat').read_bytes().decode('ascii')
            kit = json.loads(Path(folder, 'kit/kit.json').read_text(encoding='utf-8'))
            self.assertEqual(kit, {'name': '测试电路'})
            self.assertIn('测试电路.psimsch', Path(folder, 'kit/README.txt').read_text(encoding='utf-8-sig'))

    def test_script_only_change_invalidates_both_installers(self):
        with tempfile.TemporaryDirectory() as folder:
            install = [sys.executable, str(ROOT / 'scripts/install_skills.py'), '--home', folder]
            self.assertEqual(subprocess.run(install, capture_output=True, check=False).returncode, 0)
            installed = Path(folder, '.agents/skills/ad-schematic-layout/scripts/native_ad.py')
            installed.write_bytes(installed.read_bytes() + b'\n# changed\n')
            self.assertEqual(subprocess.run([*install, '--check'], capture_output=True, check=False).returncode, 1)
            if shutil.which('node'):
                node = subprocess.run(
                    ['node', str(ROOT / 'bin/cli.mjs'), 'check', '--home', folder], capture_output=True, check=False
                )
                self.assertEqual(node.returncode, 1)

    @unittest.skipUnless(shutil.which('npm') or shutil.which('npm.cmd'), 'npm 未安装')
    def test_npm_pack_excludes_private_references_and_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copy2(ROOT / 'package.json', root / 'package.json')
            files = [
                'skills/ad-schematic-layout/SKILL.md',
                'skills/ad-schematic-layout/scripts/native_ad.py',
                'skills/ad-schematic-layout/references/images/private.png',
                'skills/ad-schematic-layout/references/professional/vendor.pdf',
                'skills/ad-schematic-layout/scripts/__pycache__/private.pyc',
            ]
            for name in files:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'fixture')
            npm = 'npm.cmd' if os.name == 'nt' else 'npm'
            done = subprocess.run(
                [npm, 'pack', '--dry-run', '--ignore-scripts', '--json'], cwd=root, capture_output=True, check=False
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            data = json.loads(done.stdout)
            package = data[0] if isinstance(data, list) else next(iter(data.values()))
            packaged = {entry['path'] for entry in package['files']}
            self.assertIn(files[0], packaged)
            self.assertIn(files[1], packaged)
            self.assertFalse(packaged.intersection(files[2:]))


if __name__ == '__main__':
    unittest.main()
