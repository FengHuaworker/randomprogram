# -*- coding: utf-8 -*-
"""专项：向导连续快速切步 + 密码错误提示，验证动画重入后能回到完全不透明。"""
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

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)
from app.ui_main import MainWindow
from app.ui_dialogs import SetupWizard, AdminPasswordDialog

win = MainWindow(ad.ClassManager())
win.resize(1100, 760)
win.show()
win.startup()
store = win.store
cfg = store.load_config()


def test_wizard():
    d = SetupWizard(win, store, dict(cfg))
    d.card_advanced.set_selected(True)
    d._select_mode("advanced", True)

    def steps():
        # 模拟快速连点下一步：动画重入
        d._next()
        QTimer.singleShot(50, d._next)
        QTimer.singleShot(100, lambda: d.grab().save(str(P / "_wiz_step_after_fast.png")))
        QTimer.singleShot(700, lambda: d.grab().save(str(P / "_wiz_step_settled.png")))
        QTimer.singleShot(760, lambda: (d._back(), None))
        QTimer.singleShot(1400, lambda: d.grab().save(str(P / "_wiz_back_settled.png")))
        QTimer.singleShot(1500, d.reject)

    QTimer.singleShot(450, steps)
    rc = d.exec()
    print("wizard exec", rc, flush=True)
    QTimer.singleShot(120, test_admin)


def test_admin():
    d = AdminPasswordDialog(win)

    def wrong():
        d.edit.setText("wrong")
        d._check()
        QTimer.singleShot(500, lambda: d.grab().save(str(P / "_admin_error_settled.png")))
        QTimer.singleShot(1000, d.reject)

    QTimer.singleShot(450, wrong)
    rc = d.exec()
    print("admin exec", rc, flush=True)
    app.quit()


QTimer.singleShot(600, test_wizard)
QTimer.singleShot(30000, app.quit)
app.exec()
print("motion reentry test done", flush=True)
