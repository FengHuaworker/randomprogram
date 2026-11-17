# -*- coding: utf-8 -*-
"""被测进程：1.5 秒后弹出一个提示框，供 probe_win_frames.py 外部抓帧。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QTimer
from app import theme
from app.ui_widgets import MaterialAlert

app = QApplication(sys.argv)
QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\simsun.ttc")
theme.apply_theme(app)

host = QWidget()
host.setWindowTitle("dlg-host")
host.resize(1000, 700)
host.setStyleSheet("background:#2b2f36;")
host.show()


def open_dialog():
    dlg = MaterialAlert(host, "提示", "这是一条普通提示，用来观察弹窗入场时是否抽搐。")
    dlg.show()
    dlg.raise_()


QTimer.singleShot(1500, open_dialog)
QTimer.singleShot(6000, app.exit)
app.exec()
