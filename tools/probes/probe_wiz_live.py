# -*- coding: utf-8 -*-
"""在空数据目录里跑真实 exe：抓「配置向导」弹出过程的窗口矩形序列 + 客户区真彩图。

目的：
1) 确认向导窗口是否「先出现在默认位置、再跳到客户区」（用户说的水平跳）；
2) 用屏幕 BitBlt 按 ClientToScreen 截客户区，避免 PrintWindow 的非客户区偏移。
"""
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, ".")
import numpy as np
from PySide6.QtGui import QImage, QGuiApplication

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]


class BIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", wt.DWORD * 3)]


def grab_screen_rect(x, y, w, h):
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, w, h, hdc, x, y, 0x00CC0020)
    bi = BI()
    bi.bmiHeader.biSize = ctypes.sizeof(BIH)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    return np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4).copy()


def grab_printwindow(hwnd, w, h):
    """frameless 弹窗用 PrintWindow 抓，1:1 无非客户区偏移。"""
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)   # PW_RENDERFULLCONTENT
    if not ok:
        gdi32.BitBlt(mem, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
    bi = BI()
    bi.bmiHeader.biSize = ctypes.sizeof(BIH)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    if not ok:
        return None
    return np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4).copy()


def top_windows(pid):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            c = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(c))
            out.append((hwnd, (r.left, r.top, r.right, r.bottom),
                        (c.right - c.left, c.bottom - c.top)))
        return True

    user32.EnumWindows(cb, 0)
    return out


src = sys.argv[1] if len(sys.argv) > 1 else "发布版/随机抽号.exe"
tmp = os.path.abspath("tools/_tmp_wiz")
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp)
exe = os.path.join(tmp, "随机抽号.exe")
shutil.copy2(src, exe)

app = QGuiApplication(sys.argv[:1])
p = subprocess.Popen([exe], cwd=tmp)
try:
    t0 = time.time()
    seen = {}
    pid = None
    shot = False
    big = []
    while time.time() - t0 < 10.0:
        if pid is None:
            # 找主窗口拿 pid
            found = []

            @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
            def find(hwnd, _):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    b = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, b, n + 1)
                    if b.value == "随机抽号" and user32.IsWindowVisible(hwnd):
                        found.append(hwnd)
                        return False
                return True

            user32.EnumWindows(find, 0)
            if found:
                pp = wt.DWORD()
                user32.GetWindowThreadProcessId(found[0], ctypes.byref(pp))
                pid = pp.value
        if pid:
            for hwnd, rect, cl in top_windows(pid):
                key = (hwnd, rect)
                if key not in seen:
                    seen[key] = time.time() - t0
                    print(f"  t={seen[key]*1000:7.1f}ms hwnd={hwnd} rect={rect} client={cl}")
                    if cl[0] > 800 and cl[1] > 500 and hwnd not in big:
                        big.append(hwnd)
                    if len(big) >= 2 and not shot:
                        arr = grab_printwindow(hwnd, cl[0], cl[1])
                        if arr is not None:
                            h, w, _ = arr.shape
                            QImage(arr.data, w, h, w * 4, QImage.Format_ARGB32).save(
                                "tools/_wiz_live.png")
                            print(f"     -> PrintWindow shot {w}x{h}")
                            shot = True
        time.sleep(0.02)
    if not shot:
        print("没抓到客户区图")
finally:
    p.terminate()
    time.sleep(0.3)
