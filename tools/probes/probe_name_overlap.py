# -*- coding: utf-8 -*-
"""查「姓名遮挡提示」：在多个窗口尺寸下把抽号页切到结果态，
量 name_label 与 hint_label 在窗口坐标系里的矩形是否相交、间距多少。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from tools._probe_env import temp_classes


def rect_in(w, top):
    p = w.mapTo(top, QPoint(0, 0))
    return QRect(p, w.size())


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from app import theme
    from app.app_data import ClassManager
    from app.ui_main import MainWindow

    theme.register_fonts(str(ROOT))
    theme.apply_theme(app)
    base = temp_classes("rp_overlap_")
    win = MainWindow(ClassManager(str(base)))
    win.startup()
    win.show()

    sizes = [(1536, 830), (1400, 860), (1280, 800), (1100, 720), (1000, 680), (900, 620)]
    for w, h in sizes:
        win.resize(w, h)
        app.processEvents()
        page = win.draw_page
        # 造一个三字姓名 + 结果态
        page.num_label.set_now("08")
        page._set_state("result")
        page._set_name("陈泽恩")
        page.result.set_watermark(False)
        page._refresh_hint()
        if hasattr(page, "_stretch_grid"):
            page._stretch_grid()
        app.processEvents()
        time.sleep(0.05)
        app.processEvents()

        nr = rect_in(page.name_label, win)
        hr = rect_in(page.hint_label, win)
        cr = rect_in(page.caption, win)
        sr = rect_in(page.result, win)
        gap = hr.top() - nr.bottom() - 1
        flag = "!! 相交" if nr.intersects(hr) else "OK"
        print(f"[{w}x{h}] result h={sr.height():4d}  name {nr.y():4d}..{nr.bottom():4d} "
              f"(h={nr.height():2d})  hint {hr.y():4d}..{hr.bottom():4d} (h={hr.height():2d})  "
              f"间距 {gap:3d}px  {flag}")
        if nr.intersects(cr):
            print("      !! 姓名与标题相交")
        if hr.bottom() > sr.bottom():
            print(f"      !! 提示溢出舞台：hint.bottom={hr.bottom()} > stage.bottom={sr.bottom()}")
        if nr.bottom() > sr.bottom():
            print(f"      !! 姓名溢出舞台：{nr.bottom()} > {sr.bottom()}")

    win.close()


if __name__ == "__main__":
    main()
