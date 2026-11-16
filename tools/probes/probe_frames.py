# -*- coding: utf-8 -*-
"""逐帧抓真实窗口（numpy 向量化），量「抽号完」时内容有没有水平位移。

每帧只做两件事：
  - 卡片中线扫描左缘（页面底色 → 卡片白）→ cardLeft；
  - 舞台区域里 accent 色像素的包围盒 → 数字的左右缘与中心。
帧率能到 100+ fps，足够覆盖弹簧动画的每一帧。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from tools._probe_env import temp_classes

CARD = (255, 255, 255)
ACCENT = (94, 120, 144)


def to_np(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGBA8888)
    h, w = img.height(), img.width()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.sizeInBytes())
    arr = buf.reshape((h, img.bytesPerLine()))[:, : w * 4].reshape(h, w, 4)
    return arr


def card_left(arr, y, tol=6):
    row = arr[int(y)]
    m = (np.abs(row[:, 0].astype(int) - CARD[0]) < tol) & \
        (np.abs(row[:, 1].astype(int) - CARD[1]) < tol) & \
        (np.abs(row[:, 2].astype(int) - CARD[2]) < tol)
    # 连续 24 像素才算卡片
    idx = np.flatnonzero(m)
    if idx.size < 24:
        return None
    return int(idx[0])


def accent_bbox(arr, box, tol=26):
    x0, y0, x1, y1 = box
    sub = arr[y0:y1, x0:x1]
    m = (np.abs(sub[:, :, 0].astype(int) - ACCENT[0]) < tol) & \
        (np.abs(sub[:, :, 1].astype(int) - ACCENT[1]) < tol) & \
        (np.abs(sub[:, :, 2].astype(int) - ACCENT[2]) < tol)
    ys, xs = np.nonzero(m)
    if xs.size == 0:
        return None
    return (x0 + int(xs.min()), y0 + int(ys.min()),
            x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from app.app_data import ClassManager
    from app.ui_main import MainWindow

    base = temp_classes("rp_strip_")
    win = MainWindow(ClassManager(str(base)))
    win.startup()
    win.resize(1536, 830)
    win.show()
    app.processEvents()
    time.sleep(0.25)
    app.processEvents()

    page = win.draw_page
    hero = page.hero
    stage = page.result
    dpr = win.devicePixelRatioF()
    y_scan = int((hero.mapTo(win, QPoint(0, hero.height() // 2)).y()) * dpr)
    p0 = stage.mapTo(win, QPoint(0, 0))
    p1 = stage.mapTo(win, QPoint(stage.width(), stage.height()))
    box = (int(p0.x() * dpr), int(p0.y() * dpr), int(p1.x() * dpr), int(p1.y() * dpr))

    rows = []
    page.toggle()
    t = time.time()
    while time.time() - t < 0.30:
        app.processEvents(); time.sleep(0.01)
    page.toggle()
    t0 = time.time()
    while time.time() - t0 < 1.5:
        app.processEvents()
        arr = to_np(win.grab().toImage())
        rows.append((time.time() - t0, card_left(arr, y_scan), accent_bbox(arr, box)))
        time.sleep(0.004)

    print(f"帧数 = {len(rows)}  ({len(rows)/1.5:.0f} fps)")
    lefts = [(t, c) for t, c, _ in rows if c is not None]
    print("cardLeft 序列：", " ".join(str(c) for _, c in lefts))
    jumps = [(round(t * 1000), lefts[i - 1][1], lefts[i][1])
             for i, (t, _c) in enumerate(lefts) if i and abs(lefts[i][1] - lefts[i - 1][1]) > 0]
    print("  !! 卡片左缘变化：", jumps if jumps else "无（全程一致）")

    cen = [(t, (b[0] + b[2]) / 2) for t, _, b in rows if b is not None]
    print("数字中心x：", " ".join(f"{c:.0f}" for _, c in cen))
    j2 = [(round(t * 1000), round(cen[i - 1][1], 1), round(cen[i][1], 1))
          for i, (t, _c) in enumerate(cen) if i and abs(cen[i][1] - cen[i - 1][1]) > 1.0]
    print("  !! 数字中心跳变：", j2 if j2 else "无")

    win.close()


if __name__ == "__main__":
    main()
