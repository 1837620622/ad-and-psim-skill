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


class Gdi(Svg):
    """仿 Windows 原生出图：1 倍像素、无抗锯齿线条、ClearType 式子像素文字。

    Windows 原生导出由 GDI 绘制：线条不做抗锯齿，偶数宽的笔以坐标为中心向两侧铺开；文字按水平
    子像素渲染，边缘带彩色。这里用同样的规则和同度量字体复现，供 Mac/Linux 上提前看效果。
    """

    def __init__(
        self, width, height, scale, flip, background, y_up=True, font_files=(), font_dirs=(), offset=(0.5, 0.5)
    ):
        from PIL import Image, ImageDraw

        # scale 可为 (横向, 纵向) 像素/单位：原生导出两向比例常略有差别；offset 为坐标 0 所在的像素位置。
        self.sx, self.sy = scale if isinstance(scale, (tuple, list)) else (scale, scale)
        self.ox, self.oy = offset
        super().__init__(width, height, (self.sx + self.sy) / 2, flip, y_up)
        self.size = (math.ceil(width * self.sx), math.ceil(height * self.sy))
        self.image = Image.new('RGB', self.size, background)
        self.draw = ImageDraw.Draw(self.image)
        self.renderer = 'gdi'
        self.faces = _font_faces(font_files, font_dirs)
        self.fonts = {}
        self.font_profile = {
            family: {k: v for k, v in face.items() if k != 'path'} | {'file': face['path']}
            for family, face in self.faces.items()
        }

    def p(self, x, y):
        return x * self.sx + self.ox, ((self.flip - y) if self.y_up else y) * self.sy + self.oy

    def pen(self, width):
        return max(1, round(width * self.scale))

    @staticmethod
    def span(a, b):
        """连续坐标区间 [a, b) 覆盖的像素：像素中心落在区间内。"""
        return math.ceil(a - 0.5), math.ceil(b - 0.5) - 1

    def segment(self, a, b, stroke, w):
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        half = w / 2
        if abs(y1 - y2) < 1e-9 or abs(x1 - x2) < 1e-9:
            # 水平、竖直线：笔宽以坐标为中心，两端按方头延伸半个笔宽（1 像素笔不延伸）。
            cap = half if w > 1 else 0
            left, right = self.span(min(x1, x2) - cap, max(x1, x2) + cap + (0 if w > 1 else 1))
            top, bottom = self.span(min(y1, y2) - cap, max(y1, y2) + cap + (0 if w > 1 else 1))
            if abs(y1 - y2) < 1e-9:
                top, bottom = self.span(y1 - half, y1 + half)
            else:
                left, right = self.span(x1 - half, x1 + half)
            self.draw.rectangle((left, top, right, bottom), fill=stroke)
        else:
            self.draw.line([(x1 - 0.5, y1 - 0.5), (x2 - 0.5, y2 - 0.5)], fill=stroke, width=w)

    def lines(self, points, stroke, width, closed=False, fill=None):
        w = self.pen(width)
        if closed and fill:
            xs, ys = {q[0] for q in points}, {q[1] for q in points}
            if len(points) == 4 and len(xs) == 2 and len(ys) == 2:
                (x1, y1), (x2, y2) = self.p(min(xs), max(ys)), self.p(max(xs), min(ys))
                left, right = self.span(x1, x2)
                top, bottom = self.span(y1, y2)
                self.draw.rectangle((left, top, right, bottom), fill=fill)
            else:
                self.draw.polygon([(u - 0.5, v - 0.5) for u, v in (self.p(*q) for q in points)], fill=fill)
        path = list(points) + (list(points[:1]) if closed else [])
        for a, b in zip(path, path[1:]):
            self.segment(a, b, stroke, w)

    def ellipse(self, cx, cy, rx, ry, stroke, width, fill=None):
        x, y = self.p(cx, cy)
        x, y = x - 0.5, y - 0.5
        box = [x - rx * self.sx, y - ry * self.sy, x + rx * self.sx, y + ry * self.sy]
        self.draw.ellipse(box, fill=fill, outline=stroke, width=self.pen(width))

    def face(self, family, value):
        key = 'cjk' if _cjk(value) and 'cjk' in self.faces else family
        return self.faces.get(key) or self.faces.get('serif')

    def text(self, x, y, value, size, fill, family='serif', rotation=0, anchor='start', bold=False, italic=False):
        from PIL import Image, ImageDraw, ImageFont

        if not value:
            return
        face = self.face(family, value)
        if face is None:
            raise RuntimeError('没有找到可用的 Times New Roman/Arial 或同度量字体')
        em = max(4, round(size * self.scale))
        key = (face['path'], face.get('index', 0), em)
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(face['path'], em * 3, index=face.get('index', 0))
        font = self.fonts[key]
        horizontal = {'start': 'l', 'middle': 'm', 'end': 'r'}[anchor]
        left, top, right, bottom = font.getbbox(value, anchor=horizontal + 's')
        pad = 2
        # 三倍分辨率绘制再折回：纵向三行合一，横向保留三个子像素做 1-2-3-2-1 滤波，得到 RGB 三路覆盖率。
        ax, ay = 3 * (pad + math.ceil(-left / 3)), 3 * (pad + math.ceil(-top / 3))
        width3 = ax + 3 * (math.ceil(right / 3) + pad)
        height3 = ay + 3 * (math.ceil(bottom / 3) + pad)
        mask = Image.new('L', (width3, height3), 0)
        ImageDraw.Draw(mask).text((ax, ay), value, fill=255, font=font, anchor=horizontal + 's')
        coverage = _subpixel(_rows(mask))
        px, py = self.p(x, y)
        # GDI 把文字原点（基线）对齐到整像素。
        x0, y0 = math.floor(px + 0.5), math.floor(py + 0.5)
        ax, ay = ax // 3, ay // 3
        if rotation:
            gray = coverage.convert('L')
            coverage = Image.merge('RGB', [gray] * 3).rotate(90 * rotation, expand=True)
            w, h = width3 // 3, height3 // 3
            ax, ay = {1: (ay, w - ax), 2: (w - ax, h - ay), 3: (h - ay, ax)}[rotation % 4]
        _blend(self.image, coverage, (x0 - ax, y0 - ay), fill)

    def crop_to_ink(self, margin):
        """按墨迹范围外加 margin 像素裁切（PSIM 原生导出的取景方式）。"""
        from PIL import Image, ImageChops

        box = ImageChops.difference(
            self.image, Image.new('RGB', self.image.size, self.image.getpixel((0, 0)))
        ).getbbox()
        if box:
            left, top, right, bottom = box
            self.image = self.image.crop((left - margin, top - margin, right + margin, bottom + margin))
            self.size = self.image.size

    def save(self, path, background):
        from PIL import PngImagePlugin

        info = PngImagePlugin.PngInfo()
        info.add_text('Source', 'portable render (gdi style), not a native export')
        self.image.save(path, pnginfo=info)


# 字体：优先真正的 Times New Roman/Arial（Windows、macOS 自带），其次字宽与之逐字相同的同度量字体。
FACES = {
    'serif': (
        ('Times New Roman', True, ('times.ttf', 'Times New Roman.ttf')),
        ('Times New Roman', True, ('/System/Library/Fonts/Supplemental/Times New Roman.ttf',)),
        ('Times New Roman', True, ('/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf',)),
        (
            'Liberation Serif',
            False,
            (
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/liberation-serif/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/liberation/LiberationSerif-Regular.ttf',
                '~/Library/Fonts/LiberationSerif-Regular.ttf',
                '/Library/Fonts/LiberationSerif-Regular.ttf',
                '/opt/homebrew/share/fonts/LiberationSerif-Regular.ttf',
                'LiberationSerif-Regular.ttf',
            ),
        ),
        ('Tinos', False, ('/usr/share/fonts/truetype/croscore/Tinos-Regular.ttf', 'Tinos-Regular.ttf')),
    ),
    'sans': (
        ('Arial', True, ('arial.ttf', 'Arial.ttf')),
        ('Arial', True, ('/System/Library/Fonts/Supplemental/Arial.ttf',)),
        ('Arial', True, ('/usr/share/fonts/truetype/msttcorefonts/Arial.ttf',)),
        (
            'Liberation Sans',
            False,
            (
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf',
                '/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
                '~/Library/Fonts/LiberationSans-Regular.ttf',
                '/Library/Fonts/LiberationSans-Regular.ttf',
                '/opt/homebrew/share/fonts/LiberationSans-Regular.ttf',
                'LiberationSans-Regular.ttf',
            ),
        ),
        ('Arimo', False, ('/usr/share/fonts/truetype/croscore/Arimo-Regular.ttf', 'Arimo-Regular.ttf')),
    ),
    'cjk': (
        ('SimSun', True, ('simsun.ttc',)),
        ('Songti SC', False, ('/System/Library/Fonts/Supplemental/Songti.ttc',)),
        (
            'Noto Serif CJK',
            False,
            (
                '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
                '/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc',
            ),
        ),
        (
            'Noto Sans CJK',
            False,
            (
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                '/System/Library/Fonts/PingFang.ttc',
                '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            ),
        ),
    ),
}
FAMILY_OF = {'Times New Roman': 'serif', 'Arial': 'sans', 'SimSun': 'cjk', 'NSimSun': 'cjk'}


_FACES_CACHE = {}


def _font_faces(font_files=(), font_dirs=()):
    """解析可用字体；显式给出的字体文件按其族名覆盖自动查找的结果。结果按参数缓存。"""
    key = (tuple(str(p) for p in font_files), tuple(str(p) for p in font_dirs))
    if key not in _FACES_CACHE:
        _FACES_CACHE[key] = _find_faces(font_files, font_dirs)
    return {family: dict(face) for family, face in _FACES_CACHE[key].items()}


def _find_faces(font_files, font_dirs):
    from PIL import ImageFont

    faces = {}
    for family, choices in FACES.items():
        for name, exact, candidates in choices:
            for candidate in candidates:
                path = Path(candidate).expanduser()
                try:
                    ImageFont.truetype(str(path), 10)
                except OSError:
                    continue
                faces[family] = {'family': name, 'exact': exact, 'metric_compatible': True, 'path': str(path)}
                if family == 'cjk':
                    faces[family]['metric_compatible'] = exact
                break
            if family in faces:
                break
    explicit = [Path(p) for p in font_files]
    for directory in font_dirs:
        explicit += sorted(p for p in Path(directory).rglob('*') if p.suffix.lower() in ('.ttf', '.ttc', '.otf'))
    for path in explicit:
        try:
            name = ImageFont.truetype(str(path), 10).getname()[0]
        except OSError:
            continue
        family = FAMILY_OF.get(name)
        if family:
            faces[family] = {'family': name, 'exact': True, 'metric_compatible': True, 'path': str(path.resolve())}
    return faces


# 与原生导出逐像素比对标定：三行平均后把 20% 以下的覆盖率压为 0、80% 以上压满，接近 GDI 纵向的硬边。
TEXT_EDGE = 0.2


def _rows(mask):
    """三倍高度 → 一倍：三行平均后提高对比度。"""
    from PIL import Image

    width3, height3 = mask.size
    low, span = TEXT_EDGE * 255, 255 * (1 - 2 * TEXT_EDGE)
    lut = [max(0, min(255, round((v - low) / span * 255))) for v in range(256)]
    return mask.resize((width3, height3 // 3), Image.BOX).point(lut)


def _subpixel(mask):
    """三倍水平分辨率的覆盖率 → 每像素 RGB 三路覆盖率（类 ClearType 的 1-2-3-2-1 低通）。"""
    from PIL import Image, ImageFilter

    width3, height = mask.size
    soft = mask.filter(ImageFilter.Kernel((5, 5), [0] * 10 + [1, 2, 3, 2, 1] + [0] * 10, scale=9))
    data = soft.tobytes()
    channels = [bytearray(), bytearray(), bytearray()]
    for row in range(height):
        line = data[row * width3 : (row + 1) * width3]
        for k in range(3):
            channels[k] += line[k::3]
    width = width3 // 3
    return Image.merge('RGB', [Image.frombytes('L', (width, height), bytes(c)) for c in channels])


def _blend(image, coverage, origin, fill):
    """按三路覆盖率把文字颜色混到底图上（各通道独立，带 ClearType 的彩色边）。"""
    from PIL import Image, ImageColor

    ink = ImageColor.getrgb(fill) if isinstance(fill, str) else fill
    x, y = origin
    box = (x, y, x + coverage.width, y + coverage.height)
    clip = (max(box[0], 0), max(box[1], 0), min(box[2], image.width), min(box[3], image.height))
    if clip[0] >= clip[2] or clip[1] >= clip[3]:
        return
    coverage = coverage.crop((clip[0] - x, clip[1] - y, clip[2] - x, clip[3] - y))
    region = image.crop(clip)
    out = [
        Image.composite(Image.new('L', region.size, ink[k]), band, cov)
        for k, (band, cov) in enumerate(zip(region.split(), coverage.split()))
    ]
    image.paste(Image.merge('RGB', out), clip[:2])


def gdi_available():
    """仿原生后端需要 Pillow 和 Times New Roman（或同度量字体）。"""
    if importlib.util.find_spec('PIL') is None:
        return False
    return 'serif' in _font_faces()


def pick_renderer(target, scale, canvas_options, native_look):
    """auto 时优先仿原生（gdi），并在未指定 scale 时使用原生导出的像素比例。返回 (scale, 选项)。"""
    options = dict(canvas_options)
    renderer = options.get('renderer', 'auto')
    if (
        Path(target).suffix.lower() == '.png'
        and renderer == 'auto'
        and not options.get('skip_system_fonts')
        and gdi_available()
    ):
        renderer = options['renderer'] = 'gdi'
    if renderer == 'gdi' and scale is None:
        scale = native_look['scale']
        options.setdefault('offset', native_look['offset'])
    return (4.0 if scale is None else scale), options


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
    offset=(0.5, 0.5),
):
    """按扩展名选择 SVG 或 PNG 画布；offset 只用于 gdi 后端的像素对齐。"""
    suffix = Path(target).suffix.lower()
    flip = height if flip is None else flip
    if suffix == '.png':
        if renderer not in ('auto', 'resvg', 'pillow', 'gdi'):
            raise ValueError('renderer 须为 auto、resvg、pillow 或 gdi')
        if renderer == 'gdi':
            if skip_system_fonts:
                raise ValueError('gdi 后端按字体族查找字体；用 --font-file/--font-dir 指定，不支持禁用系统字体')
            return Gdi(width, height, scale, flip, background, y_up, font_files, font_dirs, offset)
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
    parser.add_argument(
        '--renderer',
        choices=['auto', 'resvg', 'pillow', 'gdi'],
        default='auto',
        help='auto：有 Pillow 时仿 Windows 原生出图（gdi），否则 resvg-py 或 Pillow 平滑渲染',
    )
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
