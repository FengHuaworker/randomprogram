# -*- coding: utf-8 -*-
"""极致动效展示：真实窗口触发一次抽号，抓定格瞬间（光环+弹跳）与稳定态。"""
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app.app_data as ad
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "ui_preview"

# 用临时数据目录，避免污染正式数据
TMP = Path(tempfile.mkdtemp(prefix="rp_showcase_"))
shutil.copytree(ROOT / "发布版" / "classes", TMP / "classes")
(TMP / "template").mkdir(exist_ok=True)
shutil.copy(ROOT / "发布版" / "template" / "template.txt", TMP / "template" / "template.txt")
ad.get_base_dir = lambda: TMP

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

win = MainWindow(ad.ClassManager())
win.resize(1100, 760)
win.show()
win.startup()

import ctypes
_u = ctypes.windll.user32
_h = int(win.winId())
_u.SetWindowPos(_h, -1, 80, 60, 1100, 760, 0x40)
_u.SetForegroundWindow(_h)


def shot(name):
    r = win.frameGeometry()
    ImageGrab.grab(bbox=(r.left(), r.top(), r.right(), r.bottom())).save(str(P / name))
    print(name, flush=True)


def flow():
    win.draw_page.start()                                  # 开始滚动
    QTimer.singleShot(700, win.draw_page.stop)             # 定格
    QTimer.singleShot(1060, lambda: shot("_showcase_burst.png"))   # 光环+弹跳
    QTimer.singleShot(1900, lambda: shot("_showcase_settled.png"))
    QTimer.singleShot(2100, app.quit)


QTimer.singleShot(1400, flow)   # 等首屏入场动画结束
QTimer.singleShot(5000, app.quit)
app.exec()
print("done, temp:", TMP, flush=True)
