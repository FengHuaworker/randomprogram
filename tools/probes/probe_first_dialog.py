# -*- coding: utf-8 -*-
"""测量进程中第一个弹窗的显示耗时（分层窗口首次创建的固定开销）。"""
import sys, time
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
host = QWidget(); host.resize(1180, 760)
host.setStyleSheet("background:#fff;"); host.show()
app.processEvents()

label = sys.argv[1] if len(sys.argv) > 1 else "?"
dlg = MaterialAlert(host, "提示", "首次弹窗耗时。")
t1 = time.perf_counter(); dlg._prepare_show(); t2 = time.perf_counter()
dlg.show(); t3 = time.perf_counter()
print(f"{label} prep={int((t2-t1)*1000):3d}ms show={int((t3-t2)*1000):3d}ms", flush=True)
dlg.close()
QTimer.singleShot(50, app.exit)
app.exec()
