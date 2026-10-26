"""渲染画布：同一套绘图接口输出 SVG（标准库）或 PNG（需要 Pillow）。两项技能各带一份相同的副本。"""

import html
import math
from pathlib import Path

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

    def save(self, path, background):
        width, height = self.size
        body = '\n'.join(self.items)
        Path(path).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">\n<!-- portable render, not a native export -->\n'
            f'<rect width="100%" height="100%" fill="{background}"/>\n{body}\n</svg>\n',
            encoding='utf-8',
            newline='\n',
        )


class Raster(Svg):
    """Pillow 后端：先放大绘制再缩小，线条和文字平滑。"""

    def __init__(self, width, height, scale, flip, background, supersample=2, y_up=True):
        from PIL import Image, ImageDraw

        super().__init__(width, height, scale * supersample, flip, y_up)
        self.final = (math.ceil(width * scale), math.ceil(height * scale))
        self.image = Image.new('RGB', self.size, background)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = {}

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


def open_canvas(target, width, height, scale, background, flip=None, y_up=True):
    """按扩展名选择 SVG 或 PNG 画布。"""
    suffix = Path(target).suffix.lower()
    flip = height if flip is None else flip
    if suffix == '.png':
        return Raster(width, height, scale, flip, background, y_up=y_up)
    if suffix == '.svg':
        return Svg(width, height, scale, flip, y_up)
    raise ValueError('输出须为 .png 或 .svg')
