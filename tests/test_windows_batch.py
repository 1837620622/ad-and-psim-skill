"""在真实的 Windows cmd.exe 里运行生成的 build.bat 和 run.bat（CI 的 Windows 机器上没有 AD、PSIM）。

只验证批处理本身：找 Python、调用工具、失败时给出原因并写报告、不因 pause 卡住；
中文名称、带空格的路径和带引号的 PSIM_DIR、AD_EXE 都要能正常处理。其他系统跳过。
"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout'
PSIM = ROOT / 'skills/psim-simulation-layout'
SYSTEM32 = Path(os.environ.get('SYSTEMROOT', r'C:\Windows'), 'System32')


def tool(skill, script, *arguments):
    done = subprocess.run(
        [sys.executable, str(skill / 'scripts' / script), *map(str, arguments)],
        cwd=skill,
        capture_output=True,
        check=False,
    )
    if done.returncode:
        raise AssertionError(done.stderr.decode('utf-8', errors='replace'))


def double_click(bat, *, with_python=True, **variables):
    """像双击一样运行批处理：工作目录不是包目录，PATH 里只有本测试的 Python（或没有 Python）。"""
    folders = [str(SYSTEM32)]
    if with_python:
        folders.insert(0, str(Path(sys.executable).parent))
    env = {k: v for k, v in os.environ.items() if k.upper() not in ('PATH', 'PSIM_DIR', 'AD_EXE')}
    env.update(PATH=os.pathsep.join(folders), **variables)
    done = subprocess.run(
        ['cmd', '/c', str(bat)],
        cwd=SYSTEM32.parent,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=300,
        check=False,
    )
    output = done.stdout.decode('utf-8', errors='replace') + done.stderr.decode('utf-8', errors='replace')
    return done.returncode, output


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@unittest.skipUnless(sys.platform == 'win32', '只在 Windows 上运行批处理')
class PsimBuildBat(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()) / '构建 包'
        self.addCleanup(lambda: __import__('shutil').rmtree(self.folder.parent, ignore_errors=True))
        self.kit = self.folder / 'kit'
        tool(PSIM, 'native_psim.py', 'package', PSIM / 'assets/rc-filter-plan.json', self.kit, '--name', '测试电路')

    def test_missing_psim_stops_with_a_report(self):
        # 资源管理器“复制文件地址”带引号，目录又以反斜杠结尾：都不能让批处理出错。
        code, output = double_click(
            self.kit / 'build.bat', PSIM_NO_PAUSE='1', PSIM_NO_OPEN='1', PSIM_DIR='"C:\\No Such PSIM\\"'
        )
        self.assertEqual(code, 1, output)
        self.assertIn('Build failed', output)
        report = read_json(self.kit / 'build-report.json')
        self.assertFalse(report['passed'])
        self.assertIn('PSIM_DIR', report['error'])
        self.assertTrue(report['model'].endswith('测试电路.psimsch'))
        self.assertFalse((self.kit / '测试电路.psimsch').exists())

    def test_missing_python_is_explained(self):
        code, output = double_click(self.kit / 'build.bat', with_python=False, PSIM_NO_PAUSE='1')
        self.assertEqual(code, 1, output)
        self.assertIn('Python 3.10 or newer was not found', output)
        self.assertNotIn('build-report.json', output)
        self.assertFalse((self.kit / 'build-report.json').exists())


@unittest.skipUnless(sys.platform == 'win32', '只在 Windows 上运行批处理')
class AdRunBat(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()) / '交接 任务'
        self.addCleanup(lambda: __import__('shutil').rmtree(self.folder.parent, ignore_errors=True))
        self.job = self.folder / 'job'
        tool(AD, 'native_ad.py', 'handoff', AD / 'assets/rc-filter-plan.json', self.job, '--name', '测试原理图')

    def run_bat(self):
        return double_click(self.job / 'run.bat', NATIVE_NO_PAUSE='1', AD_EXE='"C:\\No Such AD\\X2.EXE"')

    def test_missing_ad_is_reported_and_rerun_keeps_the_failed_result(self):
        code, output = self.run_bat()
        self.assertEqual(code, 1, output)
        if sys.version_info < (3, 11):
            self.assertIn('Python 3.11 or newer was not found', output)
            return
        if importlib.util.find_spec('PIL') is None:
            self.assertIn('Pillow', output)
            self.assertFalse((self.job / 'native-results').exists())
            return
        self.assertIn('Native run failed', output)
        first = read_json(self.job / 'native-results/native-result.json')
        self.assertFalse(first['passed'])
        self.assertIn('AD_EXE', first['error'])
        code, output = self.run_bat()
        self.assertEqual(code, 1, output)
        self.assertEqual(read_json(self.job / 'native-results.failed-1/native-result.json'), first)
        self.assertFalse(read_json(self.job / 'native-results/native-result.json')['passed'])


if __name__ == '__main__':
    unittest.main()
