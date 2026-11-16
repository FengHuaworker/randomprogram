# -*- coding: utf-8 -*-
"""真实应用内弹窗：屏幕抓拍入场过冲与稳定态，检查卡片边界。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app.app_data as ad
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
ad.get_base_dir = lambda: (ROOT / "发布版")
P = ROOT / "ui_preview"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from PIL import ImageGrab

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)
from app.ui_main import MainWindow
from app.ui_widgets import MaterialAlert

win = MainWindow(ad.ClassManager())
win.resize(1000, 700)
win.show()
win.startup()

import ctypes
_u = ctypes.windll.user32
_hwnd = int(win.winId())
_u.SetWindowPos(_hwnd, -1, 60, 40, 1000, 700, 0x40)
_u.SetForegroundWindow(_hwnd)


def shot(name):
    ImageGrab.grab(all_screens=True).save(str(P / name))
    print(name, flush=True)


def run():
    d = MaterialAlert(win, "动效边界验收", "检查弹窗卡片在弹簧过冲时四边是否完整。",
                      buttons=[("知道了", True)])
    QTimer.singleShot(230, lambda: shot("_dlgfx_overshoot.png"))  # 过冲期
    QTimer.singleShot(900, lambda: shot("_dlgfx_settled.png"))    # 稳定态
    QTimer.singleShot(1300, d.accept)
    QTimer.singleShot(2000, app.quit)
    d.exec()


QTimer.singleShot(700, run)
QTimer.singleShot(6000, app.quit)
app.exec()
print("done", flush=True)
