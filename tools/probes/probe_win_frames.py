# -*- coding: utf-8 -*-
"""外部进程抓弹窗真实帧：PrintWindow 轮询，量卡片包围盒。

与 probe_screen_frames.py 的区别：抓的是**另一个进程**的窗口，抓取本身不会
拖慢被测进程的事件循环（同进程内 grab 会抢走一半帧）。

卡片判定：PrintWindow 拿到的是窗口自身内容，透明区域为 0（黑），
卡片是接近纯白 → 取 R,G,B 均 > 225 的像素包围盒。

用法：python tools/probes/probe_win_frames.py [标题] [标签]
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from shot_live import grab_to_array, find_window

OUT = ROOT / "tools" / "_shots" / "_winseq"


def bbox(arr):
    if arr is None:
        return None
    rgb = arr[:, :, :3]
    mask = (rgb[:, :, 0] > 225) & (rgb[:, :, 1] > 225) & (rgb[:, :, 2] > 225)
    ys, xs = np.nonzero(mask)
    if xs.size < 800:
        return None
    return (int(xs.min()), int(ys.min()),
            int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "提示"
    label = sys.argv[2] if len(sys.argv) > 2 else "dlg"
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    app = QApplication(sys.argv)
    target = subprocess.Popen([sys.executable, str(ROOT / "tools" / "probes" / "_dlg_target.py")])

    hwnd, name = find_window(title, timeout=12.0)
    if not hwnd:
        print("没找到弹窗窗口")
        target.kill()
        return 1
    print("window:", name, hwnd)

    frames = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 1.2:
        arr = grab_to_array(hwnd)
        bb = bbox(arr)
        frames.append((round((time.perf_counter() - t0) * 1000), bb))
        i = len(frames) - 1
        if i < 60 and arr is not None:
            h, w = arr.shape[:2]
            QImage(arr.data, w, h, w * 4, QImage.Format_ARGB32).save(
                str(OUT / f"{label}_{i:02d}.png"))

    print(f"\n帧 | 时间(ms) | 卡片包围盒 | 变化")
    prev = None
    for i, (ms, bb) in enumerate(frames):
        if bb is None:
            print(f"{i:02d} | {ms:4d} | 无卡片")
            prev = None
            continue
        d = "" if prev is None else (
            f"   dx={bb[0]-prev[0]:+4d} dy={bb[1]-prev[1]:+4d}"
            f" dw={bb[2]-prev[2]:+4d} dh={bb[3]-prev[3]:+4d}")
        print(f"{i:02d} | {ms:4d} | {bb}{d}")
        prev = bb

    target.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
