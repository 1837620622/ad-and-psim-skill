"""渲染画布：SVG 使用标准库；PNG 可选 resvg-py 或 Pillow。两项技能各带一份相同的副本。"""

import hashlib
import html
import importlib.util
import math
from pathlib import Path
import struct
import zlib

FONT_FILES = {
    'serif': (
        'times.ttf',
        'Times New Roman.ttf',
        '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
        'LiberationSerif-Regular.ttf',
        'DejaVuSerif.ttf',
    ),
    'sans': (
        'arial.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        'LiberationSans-Regular.ttf',
        'DejaVuSans.ttf',
    ),
    'cjk': (
        'simsun.ttc',
        'msyh.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        'NotoSansCJK-Regular.ttc',
    ),
}


def color(value, default=0):
    """Delphi TColor（BGR 整数）转 #rrggbb。"""
    value = int(float(value)) if value not in (None, '') else default
    return f'#{value & 0xFF:02x}{(value >> 8) & 0xFF:02x}{(value >> 16) & 0xFF:02x}'


def _cjk(text):
    return any(ord(ch) > 0x2E80 for ch in text)


class Svg:
    def __init__(self, width, height, scale, flip, y_up=True):
        self.scale, self.flip, self.y_up = scale, flip, y_up
        self.size = (math.ceil(width * scale), math.ceil(height * scale))
        self.items = []
        self.renderer = 'svg'
        self.font_profile = None

    def p(self, x, y):
        return x * self.scale, ((self.flip - y) if self.y_up else y) * self.scale

    def lines(self, points, stroke, width, closed=False, fill=None):
        coords = ' '.join(f'{px:.2f},{py:.2f}' for px, py in (self.p(*q) for q in points))
        tag = 'polygon' if closed else 'polyline'
        self.items.append(
            f'<{tag} points="{coords}" fill="{fill or "none"}" stroke="{stroke}" '
            f'stroke-width="{max(width * self.scale, 0.6):.2f}" stroke-linejoin="round"/>'
        )

    def rect(self, x1, y1, x2, y2, stroke, width, fill=None):
        self.lines([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], stroke, width, True, fill)

    def ellipse(self, cx, cy, rx, ry, stroke, width, fill=None):
        x, y = self.p(cx, cy)
        self.items.append(
            f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{rx * self.scale:.2f}" ry="{ry * self.scale:.2f}" '
            f'fill="{fill or "none"}" stroke="{stroke}" stroke-width="{max(width * self.scale, 0.6):.2f}"/>'
        )

    def text(self, x, y, value, size, fill, family='serif', rotation=0, anchor='start', bold=False, italic=False):
        px, py = self.p(x, y)
        families = {
            'serif': "'Times New Roman', Times, 'Liberation Serif', serif",
            'sans': "Arial, 'Liberation Sans', Helvetica, sans-serif",
        }
        style = (' font-weight="bold"' if bold else '') + (' font-style="italic"' if italic else '')
        turn = f' transform="rotate({-90 * rotation} {px:.2f} {py:.2f})"' if rotation else ''
        self.items.append(
            f'<text x="{px:.2f}" y="{py:.2f}" font-family="{families[family]}" '
            f'font-size="{size * self.scale:.2f}" fill="{fill}" text-anchor="{anchor}"{style}{turn}>'
            f'{html.escape(value)}</text>'
        )

    def document(self, background):
        width, height = self.size
        body = '\n'.join(self.items)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">\n<!-- portable render, not a native export -->\n'
            f'<rect width="100%" height="100%" fill="{background}"/>\n{body}\n</svg>\n'
        )

    def save(self, path, background):
        Path(path).write_text(self.document(background), encoding='utf-8', newline='\n')


class Resvg(Svg):
    """可选的 Rust SVG 后端；固定 SVG 与字体输入，减少系统绘图差异。"""

    def __init__(self, *args, font_files=(), font_dirs=(), skip_system_fonts=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.renderer = 'resvg'
        self.font_files = [str(Path(p).resolve()) for p in font_files]
        self.font_dirs = [str(Path(p).resolve()) for p in font_dirs]
        if any(not Path(p).is_file() for p in self.font_files) or any(not Path(p).is_dir() for p in self.font_dirs):
            raise ValueError('字体文件或目录不存在')
        if skip_system_fonts and not (self.font_files or self.font_dirs):
            raise ValueError('禁用系统字体时必须提供字体文件或目录，避免产生缺字预览')
        self.skip_system_fonts = skip_system_fonts
        self.font_profile = {
            'uses_system_fonts': not skip_system_fonts,
            'font_files_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in self.font_files},
            'font_directories': self.font_dirs,
        }

    def save(self, path, background):
        try:
            import resvg_py
        except ImportError as error:
            raise RuntimeError('resvg 后端需要 pip install resvg-py==0.5.0') from error
        data = resvg_py.svg_to_bytes(
            svg_string=self.document(background),
            background=background,
            font_files=self.font_files or None,
            font_dirs=self.font_dirs or None,
            skip_system_fonts=self.skip_system_fonts,
        )
        if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR' or data[-8:-4] != b'IEND':
            raise RuntimeError('resvg 没有返回有效的 PNG')
        # 保留 PNG 来源元数据，便携图不能被误认为厂商原生导出。
        text = b'Source\x00portable render, not a native export'
        chunk = struct.pack('>I', len(text)) + b'tEXt' + text
        chunk += struct.pack('>I', zlib.crc32(b'tEXt' + text) & 0xFFFFFFFF)
        Path(path).write_bytes(data[:33] + chunk + data[33:])


class Raster(Svg):
    """Pillow 后端：先放大绘制再缩小，线条和文字平滑。"""

    def __init__(self, width, height, scale, flip, background, supersample=2, y_up=True):
        from PIL import Image, ImageDraw

        super().__init__(width, height, scale * supersample, flip, y_up)
        self.final = (math.ceil(width * scale), math.ceil(height * scale))
        self.image = Image.new('RGB', self.size, background)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = {}
        self.renderer = 'pillow'

    def font(self, family, size, value):
        from PIL import ImageFont

        key = ('cjk' if _cjk(value) else family, max(4, round(size)))
        if key not in self.fonts:
            self.fonts[key] = ImageFont.load_default()
            for candidate in FONT_FILES[key[0]] + FONT_FILES['serif']:
                try:
                    self.fonts[key] = ImageFont.truetype(candidate, key[1])
                    break
                except OSError:
                    continue
        return self.fonts[key]

    def lines(self, points, stroke, width, closed=False, fill=None):
        coords = [self.p(*q) for q in points]
        w = max(1, round(width * self.scale))
        if closed:
            self.draw.polygon(coords, fill=fill, outline=None)
            coords = coords + coords[:1]
        self.draw.line(coords, fill=stroke, width=w, joint='curve')

    def ellipse(self, cx, cy, rx, ry, stroke, width, fill=None):
        x, y = self.p(cx, cy)
        box = [x - rx * self.scale, y - ry * self.scale, x + rx * self.scale, y + ry * self.scale]
        self.draw.ellipse(box, fill=fill, outline=stroke, width=max(1, round(width * self.scale)))

    def text(self, x, y, value, size, fill, family='serif', rotation=0, anchor='start', bold=False, italic=False):
        from PIL import Image, ImageDraw

        face = self.font(family, size * self.scale, value)
        px, py = self.p(x, y)
        horizontal = {'start': 'l', 'middle': 'm', 'end': 'r'}[anchor]
        if not rotation:
            self.draw.text((px, py), value, fill=fill, font=face, anchor=horizontal + 's')
            return
        left, top, right, bottom = self.draw.textbbox((0, 0), value, font=face, anchor=horizontal + 's')
        layer = Image.new('RGBA', (int(right - left) + 4, int(bottom - top) + 4), (255, 255, 255, 0))
        ImageDraw.Draw(layer).text((-left + 2, -top + 2), value, fill=fill, font=face, anchor=horizontal + 's')
        turned = layer.rotate(90 * rotation, expand=True)
        ox, oy = -left + 2, -top + 2
        w, h = layer.size
        offset = {1: (oy, w - ox), 2: (w - ox, h - oy), 3: (h - oy, ox)}[rotation % 4]
        self.image.paste(turned, (int(px - offset[0]), int(py - offset[1])), turned)

    def save(self, path, background):
        from PIL import Image, PngImagePlugin

        image = self.image.resize(self.final, Image.LANCZOS)
        info = PngImagePlugin.PngInfo()
        info.add_text('Source', 'portable render, not a native export')
        image.save(path, pnginfo=info)


def open_canvas(
    target,
    width,
    height,
    scale,
    background,
    flip=None,
    y_up=True,
    renderer='auto',
    font_files=(),
    font_dirs=(),
    skip_system_fonts=False,
):
    """按扩展名选择 SVG 或 PNG 画布。"""
    suffix = Path(target).suffix.lower()
    flip = height if flip is None else flip
    if suffix == '.png':
        if renderer not in ('auto', 'resvg', 'pillow'):
            raise ValueError('renderer 须为 auto、resvg 或 pillow')
        if renderer == 'resvg' or renderer == 'auto' and importlib.util.find_spec('resvg_py') is not None:
            return Resvg(
                width,
                height,
                scale,
                flip,
                y_up=y_up,
                font_files=font_files,
                font_dirs=font_dirs,
                skip_system_fonts=skip_system_fonts,
            )
        if font_files or font_dirs or skip_system_fonts:
            raise ValueError('显式字体配置需要 resvg 后端')
        return Raster(width, height, scale, flip, background, y_up=y_up)
    if suffix == '.svg':
        if font_files or font_dirs or skip_system_fonts:
            raise ValueError('字体文件配置用于 resvg PNG；SVG 的字体由查看器加载')
        return Svg(width, height, scale, flip, y_up)
    raise ValueError('输出须为 .png 或 .svg')


def add_renderer_arguments(parser):
    parser.add_argument('--renderer', choices=['auto', 'resvg', 'pillow'], default='auto')
    parser.add_argument('--font-file', action='append', default=[], type=Path)
    parser.add_argument('--font-dir', action='append', default=[], type=Path)
    parser.add_argument('--no-system-fonts', action='store_true')


def renderer_arguments(args):
    return {
        'renderer': args.renderer,
        'font_files': args.font_file,
        'font_dirs': args.font_dir,
        'skip_system_fonts': args.no_system_fonts,
    }
