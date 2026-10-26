"""软件窗口截图：Windows 上打开原生软件并截取其窗口，保存为 PNG（只用标准库）。

两项技能各带一份相同的副本。没有原生软件的系统由调用方改用 render.py 的便携渲染。
"""

import argparse
import ctypes
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib


def write_png(path, width, height, rgb):
    """把按行排列的 RGB 字节写成 PNG。"""
    stride = width * 3
    rows = b''.join(b'\x00' + rgb[y * stride : (y + 1) * stride] for y in range(height))

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(rows, 6))
        + chunk(b'IEND', b'')
    )


class _Windows:
    """按需加载的 user32/gdi32 接口。"""

    def __init__(self):
        from ctypes import wintypes as w

        self.w = w
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.gdi = ctypes.WinDLL('gdi32', use_last_error=True)
        u, g = self.user, self.gdi
        self.enum_proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        u.EnumWindows.argtypes = [self.enum_proc, w.LPARAM]
        u.IsWindowVisible.argtypes = [w.HWND]
        u.GetWindowTextLengthW.argtypes = [w.HWND]
        u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        u.GetWindowDC.argtypes = [w.HWND]
        u.GetWindowDC.restype = w.HDC
        u.ReleaseDC.argtypes = [w.HWND, w.HDC]
        u.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
        u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [w.HWND]
        g.CreateCompatibleDC.argtypes = [w.HDC]
        g.CreateCompatibleDC.restype = w.HDC
        g.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]
        g.CreateCompatibleBitmap.restype = w.HBITMAP
        g.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
        g.SelectObject.restype = w.HGDIOBJ
        g.BitBlt.argtypes = [
            w.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            w.HDC,
            ctypes.c_int,
            ctypes.c_int,
            w.DWORD,
        ]
        g.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]
        g.DeleteObject.argtypes = [w.HGDIOBJ]
        g.DeleteDC.argtypes = [w.HDC]
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            u.SetProcessDPIAware()

    def windows(self):
        found = []

        def visit(hwnd, _):
            if self.user.IsWindowVisible(hwnd):
                size = self.user.GetWindowTextLengthW(hwnd)
                if size:
                    buffer = ctypes.create_unicode_buffer(size + 1)
                    self.user.GetWindowTextW(hwnd, buffer, size + 1)
                    pid = self.w.DWORD()
                    self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    rect = self.w.RECT()
                    self.user.GetWindowRect(hwnd, ctypes.byref(rect))
                    area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
                    found.append({'hwnd': hwnd, 'title': buffer.value, 'pid': pid.value, 'area': area})
            return True

        self.user.EnumWindows(self.enum_proc(visit), 0)
        return found

    def capture(self, hwnd):
        w = self.w
        rect = w.RECT()
        self.user.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise RuntimeError('窗口尺寸无效，可能已最小化')
        window_dc = self.user.GetWindowDC(hwnd)
        memory_dc = self.gdi.CreateCompatibleDC(window_dc)
        bitmap = self.gdi.CreateCompatibleBitmap(window_dc, width, height)
        previous = self.gdi.SelectObject(memory_dc, bitmap)
        try:
            # PW_RENDERFULLCONTENT=2 能截到 DirectX 绘制的内容；失败时退回屏幕拷贝。
            if not self.user.PrintWindow(hwnd, memory_dc, 2):
                self.gdi.BitBlt(memory_dc, 0, 0, width, height, window_dc, 0, 0, 0x00CC0020)
            header = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
            info = ctypes.create_string_buffer(header + b'\x00' * 16)
            pixels = ctypes.create_string_buffer(width * height * 4)
            if not self.gdi.GetDIBits(memory_dc, bitmap, 0, height, pixels, info, 0):
                raise RuntimeError('读取窗口像素失败')
        finally:
            self.gdi.SelectObject(memory_dc, previous)
            self.gdi.DeleteObject(bitmap)
            self.gdi.DeleteDC(memory_dc)
            self.user.ReleaseDC(hwnd, window_dc)
        bgra = pixels.raw
        rgb = bytearray(width * height * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
        return width, height, bytes(rgb)

    def fit_document(self):
        """发送 Ctrl+PageDown（AD 的“适合文档”快捷键）。"""
        for key, flags in ((0x11, 0), (0x22, 0), (0x22, 2), (0x11, 2)):
            self.user.keybd_event(key, 0, flags, 0)


def screenshot(
    document, target, exe, title_hint, timeout=180.0, settle=6.0, maximize=True, fit_keys=False, close=False
):
    """用原生软件打开文档并截取主窗口。"""
    if os.name != 'nt':
        raise RuntimeError('窗口截图需要 Windows 与原生软件')
    api = _Windows()
    document = Path(document).resolve()
    process = subprocess.Popen([str(exe), str(document)])
    start = time.monotonic()
    chosen = None
    while time.monotonic() < start + timeout:
        candidates = [w for w in api.windows() if title_hint.lower() in w['title'].lower() or w['pid'] == process.pid]
        # 先等标题里出现文档名，避免截到启动画面；过半时限后接受本进程的任何主窗口。
        pool = [w for w in candidates if document.stem.lower() in w['title'].lower()]
        if not pool and time.monotonic() > start + timeout / 2:
            pool = [w for w in candidates if w['pid'] == process.pid]
        if pool:
            chosen = max(pool, key=lambda w: w['area'])
            break
        time.sleep(1)
    if chosen is None:
        raise TimeoutError('等待软件窗口超时；确认软件能正常打开该文件')
    if maximize:
        api.user.ShowWindow(chosen['hwnd'], 3)
    api.user.SetForegroundWindow(chosen['hwnd'])
    time.sleep(settle)
    if fit_keys:
        api.fit_document()
        time.sleep(2)
    width, height, rgb = api.capture(chosen['hwnd'])
    write_png(target, width, height, rgb)
    if close and process.poll() is None:
        process.terminate()
    return {
        'screenshot': str(Path(target).resolve()),
        'source': 'native_window',
        'window_title': chosen['title'],
        'pixel_size': [width, height],
    }


def capture_window(title, target):
    """截取标题包含指定文字的已打开窗口。"""
    if os.name != 'nt':
        raise RuntimeError('窗口截图需要 Windows')
    api = _Windows()
    matches = [w for w in api.windows() if title.lower() in w['title'].lower()]
    if not matches:
        raise RuntimeError(f'没有找到标题包含 {title!r} 的窗口')
    chosen = max(matches, key=lambda w: w['area'])
    width, height, rgb = api.capture(chosen['hwnd'])
    write_png(target, width, height, rgb)
    return {
        'screenshot': str(Path(target).resolve()),
        'source': 'native_window',
        'window_title': chosen['title'],
        'pixel_size': [width, height],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('title', help='窗口标题中的文字，例如 Altium 或 PSIM')
    parser.add_argument('target', type=Path, help='输出 PNG')
    args = parser.parse_args()
    try:
        print(json.dumps(capture_window(args.title, args.target), ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
