# -*- coding: utf-8 -*-
"""快速切页残影探针：真实桌面开窗 → 高频切 Tab → 用系统截图抓真实缓冲。

输出 video/float_check/_ghost_<tag>.png
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

tag = sys.argv[1] if len(sys.argv) > 1 else "now"

app = QApplication(sys.argv)
app.setApplicationName("随机抽号")
from app import theme  # noqa: E402
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

from app.app_data import ClassManager  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402

win = MainWindow(ClassManager())
win.showMaximized()
win.raise_()
win.activateWindow()

state = {"i": 0, "n": 24}
SEQ = [0, 2, 1, 4, 3, 2, 0, 4, 1, 3] * 3

def sweep():
    i = state["i"]
    if i >= state["n"]:
        QTimer.singleShot(90, shoot)
        return
    win._on_nav_changed(SEQ[i % len(SEQ)])
    state["i"] = i + 1
    QTimer.singleShot(26, sweep)

def dump():
    print("winOpacity", win.windowOpacity())
    for name, pg in (("draw", win.draw_page), ("hist", win.history_page),
                     ("stats", win.stats_page), ("conf", win.config_page),
                     ("shield", win.shield_page)):
        eff = pg.graphicsEffect()
        if eff is None:
            print(f"  {name}: no effect")
            continue
        print(f"  {name}: a={eff.a:.3f} s={eff.s:.3f} dy={eff.dy:.2f} "
              f"enabled={eff.isEnabled()} "
              f"cur={win.stack.indexOf(pg)==win.stack.currentIndex()}")


def shoot():
    from PIL import ImageGrab
    im = ImageGrab.grab(bbox=(0, 0, 1280, 900))
    out = ROOT / "video" / "float_check" / f"_ghost_{tag}.png"
    im.save(out)
    dump()
    print("saved", out, im.size)
    win.close()
    app.quit()

QTimer.singleShot(1600, sweep)
app.exec()
