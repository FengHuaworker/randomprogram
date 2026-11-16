# -*- coding: utf-8 -*-
"""复现：连点批量抽号 +/- 后数字位置漂移，自截图取证。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app.app_data as ad
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ad.get_base_dir = lambda: (ROOT / "发布版")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)
from app.ui_main import MainWindow

win = MainWindow(ad.ClassManager())
W, H = 1000, 700
OUT_BEFORE = ROOT / "ui_preview" / "_step_before.png"
OUT_MID = ROOT / "ui_preview" / "_step_mid.png"
OUT_AFTER = ROOT / "ui_preview" / "_step_after.png"
win.resize(W, H)
win.show()
win.startup()

stepper = win.draw_page.stepper


def _before():
    win.grab().save(str(OUT_BEFORE))
    print("before saved", flush=True)


def _clicks():
    # 模拟用户快速连点 plus（间隔小于 280ms 动画时长），共 14 次
    n = {"i": 0}

    def one():
        stepper.btn_plus.click()
        n["i"] += 1
        if n["i"] < 14:
            QTimer.singleShot(70, one)
        else:
            QTimer.singleShot(70, _mid)
            QTimer.singleShot(900, _after)

    one()


def _mid():
    # 动画进行中：检查数字有没有因偏移被裁切
    win.grab().save(str(OUT_MID))
    print("mid saved; bump =", stepper.value_label.get_bump(), flush=True)


def _after():
    win.grab().save(str(OUT_AFTER))
    print("after saved; value_label pos =", stepper.value_label.pos(),
          "geometry =", stepper.value_label.geometry(), flush=True)
    print("stepper pos =", stepper.pos(), "size =", stepper.size(), flush=True)


QTimer.singleShot(1500, _before)
QTimer.singleShot(1700, _clicks)
QTimer.singleShot(6500, app.quit)
app.exec()
print("stepper test done")
