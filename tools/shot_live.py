# -*- coding: utf-8 -*-
"""给正在运行的真实 exe 窗口截一张图（PrintWindow，不依赖桌面合成）。

用途：验证打包后的 exe 实际渲染出的字体/遮挡，而不是源码在 offscreen 下的样子。
用法：python tools/shot_live.py <exe 路径> <输出 png> [等待秒数] [窗口标题]
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def find_window(title_part: str, timeout=25.0):
    end = time.time() + timeout
    while time.time() < end:
        found = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(hwnd, _):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if title_part in buf.value and user32.IsWindowVisible(hwnd):
                    found.append((hwnd, buf.value))
            return True

        user32.EnumWindows(cb, 0)
        # 启动标识也是同名窗口：取客户区最大的那个（主窗口）
        best, best_area = None, 0
        for hwnd, name in found:
            r = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            area = (r.right - r.left) * (r.bottom - r.top)
            if area > best_area:
                best, best_area = (hwnd, name), area
        if best and best_area > 400 * 300:
            return best
        time.sleep(0.4)
    return None, None


def grab(hwnd, out_png: Path):
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 10 or h < 10:
        return False
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    if not ok:
        gdi32.BitBlt(mem, 0, 0, w, h, hdc, 0, 0, SRCCOPY)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    from PySide6.QtGui import QImage, QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    img = QImage(buf, w, h, w * 4, QImage.Format_ARGB32)
    img.save(str(out_png))

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return True


def grab_to_array(hwnd):
    """PrintWindow 到内存位图 → numpy (h, w, 4) BGRX。失败返回 None。"""
    import numpy as np
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 200 or h < 200:
        return None
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    if not ok:
        gdi32.BitBlt(mem, 0, 0, w, h, hdc, 0, 0, SRCCOPY)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4).copy()


def main():
    exe = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
    title = sys.argv[4] if len(sys.argv) > 4 else "随机抽号"
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    try:
        hwnd, name = find_window(title)
        if not hwnd:
            print("没找到窗口")
            return 1
        time.sleep(wait)
        print("window:", name, hwnd)
        ok = grab(hwnd, out)
        print("saved" if ok else "grab failed", out)
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
