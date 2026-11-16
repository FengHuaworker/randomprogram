# -*- coding: utf-8 -*-
"""小窗布局实拍验证：加载发布版数据（只看不写），按指定尺寸显示并自截图。"""
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
W = int(sys.argv[1]) if len(sys.argv) > 1 else 686
H = int(sys.argv[2]) if len(sys.argv) > 2 else 600
OUT = ROOT / "ui_preview" / f"_layout_{W}x{H}.png"
win.resize(W, H)
win.show()
win.startup()


def _snap():
    # 自己 grab 自己：不依赖前台窗口状态，抓到的一定是本应用内容
    win.grab().save(str(OUT))
    print("snapshot:", OUT.name, flush=True)


QTimer.singleShot(2000, _snap)
QTimer.singleShot(6000, app.quit)
app.exec()
print("layout test done", W, H)
