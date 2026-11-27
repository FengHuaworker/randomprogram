# -*- coding: utf-8 -*-
"""残影判定探针：把新页面强行停在 a=0.6，看底下露出的到底是「上一页」还是底色。

露出上一页 = 有残影；只有纯底色 = 正常。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app import theme  # noqa: E402
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

from app import motion  # noqa: E402
from app.app_data import ClassManager  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402

win = MainWindow(ClassManager())
win.showMaximized()
win.raise_()
win.activateWindow()


def step1():
    # 先在「抽号记录」页停稳（有表头 + 数据行，最容易看出残影）
    win.stack.setCurrentIndex(1)
    QTimer.singleShot(600, step2)


def step2():
    # 直接切到屏蔽页，不走进场动画
    win.stack.setCurrentIndex(4)
    win.stack.repaint()          # 真实路径里 _on_nav_changed 就是这么做的
    page = win.shield_page
    eff = motion._effect(page)
    eff.invalidate()
    eff.set_values(s=1.0, dx=0.0, dy=0.0, a=0.6, rot=0.0)
    eff.setEnabled(True)
    page.update()
    QTimer.singleShot(250, shoot)


def shoot():
    from PIL import ImageGrab
    out = ROOT / "video" / "float_check" / "_bleed_probe.png"
    ImageGrab.grab(bbox=(0, 0, 1280, 900)).save(out)
    print("saved", out)
    win.close()
    app.quit()


QTimer.singleShot(1500, step1)
app.exec()
