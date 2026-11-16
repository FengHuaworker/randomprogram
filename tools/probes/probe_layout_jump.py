# -*- coding: utf-8 -*-
"""在多个窗口尺寸下跑「抽号 → 定格」，报告内容区是否发生水平位移。

只看两个东西：
  1. content 视口宽度 / hero 卡片可见宽度在一轮抽号前后是否变化（= 滚动条出现/消失）；
  2. 任何子控件的中心 x 是否变化。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget

from tools._probe_env import temp_classes

SIZES = [(1536, 830), (1280, 800), (1180, 760), (1100, 720), (1000, 680), (920, 640)]


def center_x(w, top):
    p = w.mapTo(top, QPoint(0, 0))
    return p.x() + w.width() / 2.0


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from app.app_data import ClassManager
    from app.ui_main import MainWindow

    base = temp_classes("rp_sweep_")
    for size in SIZES:
        win = MainWindow(ClassManager(str(base)))
        win.startup()
        win.resize(*size)
        win.show()
        app.processEvents()
        page = win.draw_page
        labels = {"scroll.viewport": page.scroll.viewport(), "content": page.content,
                  "hero": page.hero, "result": page.result, "num": page.num_label}

        def snap():
            return {k: (w.width(), center_x(w, win)) for k, w in labels.items()}

        before = snap()
        page.toggle()
        for _ in range(10):
            app.processEvents(); time.sleep(0.01)
        page.toggle()
        t = time.time()
        mid = None
        while time.time() - t < 1.4:
            app.processEvents(); time.sleep(0.008)
            if mid is None and time.time() - t > 0.6:
                mid = snap()
        after = snap()
        diffs = []
        for k in before:
            if abs(before[k][0] - after[k][0]) > 0.5 or abs(before[k][1] - after[k][1]) > 0.5:
                diffs.append(f"{k}: w {before[k][0]}->{after[k][0]} "
                             f"cx {before[k][1]:.1f}->{after[k][1]:.1f}")
        print(f"\n[{size[0]}x{size[1]}] 视口 {before['scroll.viewport']} -> {after['scroll.viewport']}")
        print(f"   hero 宽 {before['hero'][0]} -> {after['hero'][0]}   中心x "
              f"{before['hero'][1]:.1f} -> {after['hero'][1]:.1f}")
        if diffs:
            for d in diffs:
                print("   !! " + d)
        else:
            print("   无水平位移")
        win.close()
        app.processEvents()


if __name__ == "__main__":
    main()
