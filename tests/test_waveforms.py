"""波形曲线与 XLSX：数据原样进表、超长分表、尖峰不被抽稀、预仿真不冒充交付结果。"""

import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PSIM = ROOT / 'skills/psim-simulation-layout/scripts'
# 放在末尾：同名模块仍按其他测试的约定先找 AD 副本，waveforms 只有 PSIM 有。
sys.path.append(str(PSIM))
import waveforms  # noqa: E402

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HAS_PILLOW = importlib.util.find_spec('PIL') is not None


def write_csv(path, header, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, lineterminator='\r\n')
        writer.writerow(header)
        writer.writerows(rows)
    return path


def read_xlsx(path):
    """只用标准库读回工作表：{表名: [[单元格值...]...]}。"""
    with zipfile.ZipFile(path) as archive:
        self_check = archive.testzip()
        assert self_check is None, self_check
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        names = [sheet.get('name') for sheet in book.find('s:sheets', NS)]
        sheets = {}
        for number, name in enumerate(names, 1):
            root = ET.fromstring(archive.read(f'xl/worksheets/sheet{number}.xml'))
            rows = []
            for row in root.find('s:sheetData', NS):
                values = []
                for cell in row:
                    if cell.get('t') == 'inlineStr':
                        values.append(cell.find('s:is/s:t', NS).text)
                    else:
                        values.append(float(cell.find('s:v', NS).text))
                rows.append(values)
            sheets[name] = rows
    return sheets


class Workbook(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.folder, ignore_errors=True))
        self.rows = [[i * 1e-6, 0.5 * i, 10.0, -i / 3] for i in range(50)]
        self.csv = write_csv(self.folder / 'native.csv', ['Time', 'Vout', 'Vin', '电流'], self.rows)

    def test_every_sample_lands_in_the_sheet_and_output_is_reproducible(self):
        result = waveforms.waveforms(self.csv, self.folder / 'a')
        sheets = read_xlsx(result['xlsx'])
        self.assertEqual(list(sheets), ['波形数据', '统计'])
        self.assertEqual(sheets['波形数据'][0], ['Time', 'Vout', 'Vin', '电流'])
        self.assertEqual(sheets['波形数据'][1:], self.rows)
        stats = {row[0]: row[1:] for row in sheets['统计'] if row and row[0] in ('Vout', 'Vin', '电流')}
        self.assertEqual(stats['Vout'][:3], [0.0, 24.5, 24.5])
        self.assertAlmostEqual(stats['Vin'][3], 10.0)
        self.assertEqual(result['samples'], 50)
        again = waveforms.waveforms(self.csv, self.folder / 'b')
        self.assertEqual(Path(result['xlsx']).read_bytes(), Path(again['xlsx']).read_bytes())
        self.assertEqual(Path(result['plot']).read_bytes(), Path(again['plot']).read_bytes())
        self.assertEqual(result['plot_format'], 'png' if HAS_PILLOW else 'svg')

    def test_rows_beyond_the_excel_limit_continue_on_the_next_sheet(self):
        with mock.patch.object(waveforms, 'MAX_ROWS', 21):
            result = waveforms.waveforms(self.csv, self.folder, signals=['Vout'])
        sheets = read_xlsx(result['xlsx'])
        self.assertEqual(list(sheets), ['波形数据', '波形数据 2', '波形数据 3', '统计'])
        data = [row for name in ('波形数据', '波形数据 2', '波形数据 3') for row in sheets[name][1:]]
        self.assertEqual(data, [[r[0], r[1]] for r in self.rows])
        self.assertTrue(all(sheets[name][0] == ['Time', 'Vout'] for name in list(sheets)[:3]))

    def test_time_window_and_signal_choice(self):
        result = waveforms.waveforms(self.csv, self.folder, 'win', ['Vin'], start=9.5e-6, end=19.5e-6, svg=True)
        self.assertEqual(result['samples'], 10)
        self.assertEqual(result['plotted'], ['Vin'])
        self.assertTrue(Path(result['plot']).read_text(encoding='utf-8').startswith('<svg'))
        with self.assertRaises(ValueError):
            waveforms.waveforms(self.csv, self.folder, signals=['Nope'])

    def test_bad_time_leaves_no_half_written_workbook(self):
        bad = write_csv(self.folder / 'bad.csv', ['Time', 'V'], [[0, 1], [2e-6, 1], [1e-6, 1]])
        with self.assertRaises(ValueError):
            waveforms.waveforms(bad, self.folder / 'out')
        self.assertEqual(list((self.folder / 'out').iterdir()), [])

    def test_presim_output_is_named_so_delivery_skips_it(self):
        from deliver import classify

        presim = write_csv(self.folder / 'presim.csv', ['Time', 'V'], [[0, 0], [1e-6, 1]])
        result = waveforms.waveforms(presim, self.folder / 'p')
        self.assertTrue(Path(result['xlsx']).name.startswith('presim-'))
        for path in (result['xlsx'], result['plot']):
            self.assertEqual(classify(Path(path).relative_to(self.folder)), 'archive')
        self.assertEqual(classify(Path('result/waveforms.xlsx')), 'deliver')


class Envelope(unittest.TestCase):
    def test_single_sample_spike_survives_and_ticks_read_cleanly(self):
        folder = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        rows = [[i * 1e-7, 5.0 + (30.0 if i == 77_777 else 0.0)] for i in range(200_000)]
        source = write_csv(folder / 'native.csv', ['Time', 'I(L1)'], rows)
        header, time, chosen = waveforms._columns(source, None)
        bins = waveforms._envelope(source, time, chosen, None, None, 0.0, rows[-1][0], 1000)
        self.assertEqual(max(cell[2] for cell in bins[0] if cell), 35.0)
        result = waveforms.waveforms(source, folder)
        self.assertEqual(result['summary']['I(L1)']['max'], 35.0)
        self.assertEqual(waveforms._labels([0, 2.5, 5, 7.5], 2.5)[0], ['0', '2.5', '5.0', '7.5'])
        self.assertEqual(waveforms._labels([0, 0.025, 0.05], 0.025)[0], ['0', '25m', '50m'])
        self.assertEqual(waveforms._time_axis(1e-6, 2e-3)[4], 'Time (ms)')


if __name__ == '__main__':
    unittest.main()
