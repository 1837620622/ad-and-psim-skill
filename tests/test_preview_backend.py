"""可选 PNG 后端的真实渲染及字体约束；不把便携图当成原生导出。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
AD = ROOT / 'skills/ad-schematic-layout/scripts'
PSIM = ROOT / 'skills/psim-simulation-layout/scripts'
sys.path.insert(0, str(AD))
from canvas import open_canvas


class FontConfiguration(unittest.TestCase):
    def test_no_system_fonts_requires_explicit_fonts(self):
        with self.assertRaisesRegex(ValueError, '必须提供字体'):
            open_canvas('out.png', 20, 20, 1, '#ffffff', renderer='resvg', skip_system_fonts=True)

    def test_svg_does_not_silently_ignore_explicit_font_files(self):
        with self.assertRaisesRegex(ValueError, '查看器'):
            open_canvas('out.svg', 20, 20, 1, '#ffffff', font_files=['font.ttf'])

    def test_missing_font_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '不存在'):
            open_canvas('out.png', 20, 20, 1, '#ffffff', renderer='resvg', font_files=['missing-font.ttf'])


@unittest.skipUnless(importlib.util.find_spec('resvg_py'), '可选 resvg-py 未安装')
class ResvgRendering(unittest.TestCase):
    def test_both_clis_generate_png_with_portable_provenance(self):
        for script in (AD / 'native_ad.py', PSIM / 'native_psim.py'):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as folder:
                image = Path(folder, 'draft.png')
                plan = script.parent.parent / 'assets/rc-filter-plan.json'
                done = subprocess.run(
                    [sys.executable, str(script), 'render', str(plan), str(image), '--renderer', 'resvg'],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                result = json.loads(done.stdout)
                self.assertEqual(result['renderer'], 'resvg')
                self.assertFalse(result['native_verified'])
                raw = image.read_bytes()
                self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
                offset, chunks = 8, []
                while offset < len(raw):
                    length = struct.unpack_from('>I', raw, offset)[0]
                    kind, data = raw[offset + 4 : offset + 8], raw[offset + 8 : offset + 8 + length]
                    crc = struct.unpack_from('>I', raw, offset + 8 + length)[0]
                    self.assertEqual(zlib.crc32(kind + data) & 0xFFFFFFFF, crc)
                    chunks.append((kind, data))
                    offset += length + 12
                self.assertIn((b'tEXt', b'Source\x00portable render, not a native export'), chunks)
                self.assertEqual(chunks[-1][0], b'IEND')
                self.assertTrue(zlib.decompress(b''.join(data for kind, data in chunks if kind == b'IDAT')))

    def test_same_svg_and_system_font_state_produce_identical_png(self):
        with tempfile.TemporaryDirectory() as folder:
            images = [Path(folder, name) for name in ('first.png', 'second.png')]
            for image in images:
                canvas = open_canvas(image, 100, 40, 1, '#ffffff', renderer='resvg')
                canvas.text(10, 20, 'RC 100 Ohm', 12, '#000000')
                canvas.save(image, '#ffffff')
            self.assertEqual(images[0].read_bytes(), images[1].read_bytes())


if __name__ == '__main__':
    unittest.main()
