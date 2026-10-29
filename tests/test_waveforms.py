"""波形曲线与 XLSX：Excel 表是 CSV 的逐格副本、超长分表、尖峰不被抽稀、预仿真不冒充交付结果。"""

import csv
import importlib.util
from pathlib import Path
import shutil
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


def write_csv(path, header, rows, encoding='utf-8-sig'):
    with open(path, 'w', newline='', encoding=encoding) as stream:
        writer = csv.writer(stream, lineterminator='\r\n')
        writer.writerow(header)
        writer.writerows(rows)
    return path


def read_xlsx(path, raw=False):
    """只用标准库读回工作表：{表名: [[单元格值...]...]}；raw=True 时数字给 <v> 原文，并带行号。"""
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
                        text = cell.find('s:v', NS).text
                        values.append(text if raw else float(text))
                rows.append((int(row.get('r')), values) if raw else values)
            sheets[name] = rows
    return sheets


class Workbook(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.rows = [[i * 1e-6, 0.5 * i, 10.0, -i / 3] for i in range(50)]
        self.csv = write_csv(self.folder / 'native.csv', ['Time', 'Vout', 'Vin', '电流'], self.rows)

    def test_sheet_is_the_whole_csv_and_output_is_reproducible(self):
        result = waveforms.waveforms(self.csv, self.folder / 'a')
        sheets = read_xlsx(result['xlsx'])
        self.assertEqual(list(sheets), ['native'])
        self.assertEqual(sheets['native'], [['Time', 'Vout', 'Vin', '电流'], *self.rows])
        check = {'identical': True, 'data_rows': 50, 'columns': 4, 'cells': 204, 'sheets': ['native']}
        self.assertEqual(result['xlsx_check'], check)
        self.assertEqual(result['summary']['Vout']['max'], 24.5)
        self.assertEqual(result['samples'], 50)
        again = waveforms.waveforms(self.csv, self.folder / 'b')
        self.assertEqual(Path(result['xlsx']).read_bytes(), Path(again['xlsx']).read_bytes())
        self.assertEqual(Path(result['plot']).read_bytes(), Path(again['plot']).read_bytes())
        self.assertEqual(result['plot_format'], 'png' if HAS_PILLOW else 'svg')

    def test_numbers_keep_their_csv_text_and_text_cells_stay_text(self):
        lines = [
            'Time,V(out),note,,extra',
            '0.0000000e+000,1.0000000e-005,start,,',
            '',
            '+1.0000000e-006,-0.5, 有空格 ,"a,b",007',
            '2E-6,.5,"两行\r\n文字",1.,nan',
        ]
        source = self.folder / 'native.csv'
        source.write_bytes(('\ufeff' + '\r\n'.join(lines) + '\r\n').encode('utf-8'))
        result = waveforms.waveforms(source, self.folder / 'out', svg=True)
        sheet = read_xlsx(result['xlsx'], raw=True)['native']
        self.assertEqual(
            sheet,
            [
                (1, ['Time', 'V(out)', 'note', 'extra']),  # 这里只列有值的格，列位置在下面核对
                (2, ['0.0000000e+000', '1.0000000e-005', 'start']),
                (4, ['1.0000000e-006', '-0.5', ' 有空格 ', 'a,b', '007']),
                (5, ['2E-6', '.5', '两行\r\n文字', '1.', 'nan']),
            ],
        )
        with zipfile.ZipFile(result['xlsx']) as archive:
            xml = archive.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn('<c r="E1" t="inlineStr">', xml)  # 表头空格的列位置不变：extra 仍在 E 列
        self.assertIn('<c r="E4"><v>007</v></c>', xml)
        self.assertIn('<c r="E5" t="inlineStr">', xml)  # nan 不是有限数，按文字原样保留
        self.assertEqual(result['xlsx_check']['data_rows'], 3)
        self.assertEqual(result['samples'], 3)

    def test_gb18030_csv_from_chinese_excel(self):
        source = write_csv(self.folder / '波形.csv', ['Time', '输出电压'], [[0, 1], [1e-6, 2]], 'gb18030')
        result = waveforms.waveforms(source, self.folder / 'out', svg=True)
        self.assertEqual(read_xlsx(result['xlsx'])['波形'], [['Time', '输出电压'], [0.0, 1.0], [1e-6, 2.0]])
        self.assertEqual(result['signals'], ['输出电压'])

    def test_rows_beyond_the_excel_limit_continue_on_the_next_sheet(self):
        with mock.patch.object(waveforms, 'MAX_ROWS', 21):
            result = waveforms.waveforms(self.csv, self.folder, signals=['Vout'])
        sheets = read_xlsx(result['xlsx'])
        self.assertEqual(list(sheets), ['native', 'native (2)', 'native (3)'])
        self.assertEqual(result['sheets'], list(sheets))
        self.assertEqual([row for rows in sheets.values() for row in rows[1:]], self.rows)
        self.assertTrue(all(rows[0] == ['Time', 'Vout', 'Vin', '电流'] for rows in sheets.values()))
        self.assertTrue(result['xlsx_check']['identical'])

    def test_signals_and_time_window_only_shape_the_plot(self):
        result = waveforms.waveforms(self.csv, self.folder, 'win', ['Vin'], start=9.5e-6, end=19.5e-6, svg=True)
        self.assertEqual(result['samples'], 10)
        self.assertEqual(result['plotted'], ['Vin'])
        self.assertEqual(list(result['summary']), ['Vin'])
        self.assertTrue(Path(result['plot']).read_text(encoding='utf-8').startswith('<svg'))
        self.assertEqual(read_xlsx(result['xlsx'])['native'][1:], self.rows)
        with self.assertRaises(ValueError):
            waveforms.waveforms(self.csv, self.folder, signals=['Nope'])

    def test_verify_catches_any_changed_cell(self):
        result = waveforms.waveforms(self.csv, self.folder / 'out', svg=True)
        book = Path(result['xlsx'])

        def tamper(old, new):
            copy = self.folder / 'tampered.xlsx'
            with zipfile.ZipFile(book) as source, zipfile.ZipFile(copy, 'w') as target:
                for item in source.infolist():
                    data = source.read(item)
                    if item.filename == 'xl/worksheets/sheet1.xml':
                        self.assertIn(old, data)
                        data = data.replace(old, new, 1)
                    target.writestr(item, data)
            return copy

        for old, new in (
            (b'<v>2.5</v>', b'<v>2.50</v>'),  # 数值相同、原文不同也算不同
            (b'<row r="51">', b'<row r="52">'),
            (b'\xe7\x94\xb5\xe6\xb5\x81', b'I'),  # 表头「电流」
            (b'</sheetData>', b'<row r="60"><c r="A60"><v>1</v></c></row></sheetData>'),
        ):
            with self.subTest(new=new), self.assertRaises(ValueError):
                waveforms.verify_workbook(self.csv, tamper(old, new))
        self.assertTrue(waveforms.verify_workbook(self.csv, book)['identical'])

    def test_cells_excel_cannot_hold_fail_without_leaving_a_file(self):
        bad = self.folder / 'bad.csv'
        bad.write_text('Time,V,note\n0,1,ok\n1e-6,2,bell\x07\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            waveforms.waveforms(bad, self.folder / 'out', svg=True)
        self.assertFalse((self.folder / 'out/waveforms.xlsx').exists())

    def test_sheet_titles_follow_the_csv_name(self):
        self.assertEqual(next(waveforms._titles('History')), 'History_')
        titles = waveforms._titles('a' * 40 + ':x')
        self.assertEqual(next(titles), 'a' * 31)
        self.assertEqual(next(titles), 'a' * 27 + ' (2)')

    def test_bad_time_leaves_no_half_written_workbook(self):
        for rows in ([[0, 1], [2e-6, 1], [1e-6, 1]], [[1e-6, 1], [1e-6, 2]]):
            bad = write_csv(self.folder / 'bad.csv', ['Time', 'V'], rows)
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                waveforms.waveforms(bad, self.folder / 'out')
            self.assertFalse((self.folder / 'out').exists())

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
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
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
