# -*- coding: utf-8 -*-
"""对**真实运行的 exe** 逐帧截图，量抽号结束后内容有没有水平位移。

流程：启动 exe → 找主窗口 → PostMessage 空格（开始）→ 再空格（停止）
→ 之后 1.6s 内每 ~40ms PrintWindow 抓一帧 → 量卡片左缘与数字包围盒。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.shot_live import find_window, grab_to_array  # noqa

user32 = ctypes.windll.user32
VK_SPACE = 0x20
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101


def press(hwnd, vk=VK_SPACE):
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.02)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)


def main():
    exe = Path(sys.argv[1]).resolve()
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    try:
        hwnd, name = find_window("随机抽号")
        print("window", name, hwnd, flush=True)
        time.sleep(5.0)
        press(hwnd)          # 开始
        time.sleep(0.45)
        press(hwnd)          # 停止 → 定格
        rows = []
        t0 = time.time()
        while time.time() - t0 < 1.8:
            arr = grab_to_array(hwnd)
            if arr is not None:
                rows.append((time.time() - t0, arr))
            time.sleep(0.01)
        print("帧数", len(rows))
        if not rows:
            return 1
        h, w, _ = rows[0][1].shape
        print("窗口像素", w, h)
        # 卡片左缘：在卡片中线高度上找连续白像素
        y = int(h * 0.30)
        lefts, nums = [], []
        for t, a in rows:
            row = a[y]
            white = np.all(np.abs(row[:, :3].astype(int) - 255) < 6, axis=1)
            idx = np.flatnonzero(white)
            # 连续 40 像素才算卡片
            left = None
            if idx.size:
                run = 1
                for i in range(1, idx.size):
                    run = run + 1 if idx[i] == idx[i - 1] + 1 else 1
                    if run >= 40:
                        left = int(idx[i - run + 1]); break
            lefts.append((t, left))
            # accent 色（大数字）
            sub = a[int(h * 0.15):int(h * 0.55), int(w * 0.15):int(w * 0.60), :3].astype(int)
            m = (np.abs(sub[:, :, 0] - 94) < 30) & (np.abs(sub[:, :, 1] - 120) < 30) \
                & (np.abs(sub[:, :, 2] - 144) < 30)
            ys, xs = np.nonzero(m)
            nums.append(None if xs.size == 0 else (int(xs.min()), int(xs.max())))
        ls = [l for _, l in lefts if l is not None]
        print("卡片左缘序列:", " ".join(str(v) for v in ls))
        jumps = [(round(lefts[i][0] * 1000), ls[i - 1], ls[i]) for i in range(1, len(ls)) if ls[i] != ls[i - 1]]
        print("跳变:", jumps if jumps else "无")
        ns = [(round(t * 1000), n[0], n[1]) for (t, _), n in zip(lefts, nums) if n]
        print("数字左右缘:", " ".join(f"{a0}-{a1}" for _, a0, a1 in ns[:40]))
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
