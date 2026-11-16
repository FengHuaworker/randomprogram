# -*- coding: utf-8 -*-
"""追踪弹窗窗口矩形的时间序列：确认「弹出时先出现在别处、再跳到位」。

从外部枚举该进程的所有顶层窗口，每 8ms 记一次 rect。若出现两个明显不同的
rect 且第二个稳定，就是 Qt 先按默认位置 map 再被我们摆正 —— 用户看到的
「水平跳一下」。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

sys.path.insert(0, ".")
user32 = ctypes.windll.user32
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202


def windows_of(pid):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, b, n + 1)
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        c = wt.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(c))
        out.append((hwnd, b.value, (r.left, r.top, r.right, r.bottom),
                    (c.right - c.left, c.bottom - c.top)))
        return True

    user32.EnumWindows(cb, 0)
    return out


exe = sys.argv[1] if len(sys.argv) > 1 else "发布版/随机抽号_极致动效版.exe"
p = subprocess.Popen([exe], cwd="发布版")
try:
    time.sleep(5.0)
    # onefile 会再起一个子进程持有真实窗口：先按标题找到主窗口，再用它的 pid
    box = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def find(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, b, n + 1)
            if "随机抽号" in b.value and user32.IsWindowVisible(hwnd):
                box.append(hwnd)
                return False
        return True

    user32.EnumWindows(find, 0)
    if not box:
        raise SystemExit("没找到主窗口")
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(box[0], ctypes.byref(pid))
    app_pid = pid.value
    main_hwnd = max(windows_of(app_pid), key=lambda w: w[3][0] * w[3][1])
    print("主窗口:", main_hwnd[1], main_hwnd[2], "client", main_hwnd[3], "pid", app_pid)
    time.sleep(0.6)

    lp = (52 << 16) | 1878            # 设置按钮（客户区坐标）
    user32.PostMessageW(main_hwnd[0], WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.04)
    user32.PostMessageW(main_hwnd[0], WM_LBUTTONUP, 0, lp)

    prev = None
    t0 = time.time()
    while time.time() - t0 < 2.0:
        ws = [w for w in windows_of(app_pid) if w[0] != main_hwnd[0]]
        if ws:
            w = max(ws, key=lambda x: x[2][2] * x[2][3])
            key = w[2]
            if key != prev:
                print(f"  t={(time.time()-t0)*1000:7.1f}ms  hwnd={w[0]} "
                      f"name={w[1]!r} rect={w[2]} client={w[3]}")
                prev = key
        time.sleep(0.008)
finally:
    p.terminate()
