# -*- coding: utf-8 -*-
"""滚动中每帧绘制成本归因：记录 1 秒内所有 Paint 事件的目标与区域。
用法：python tools/probe_rolling_paint.py
"""
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

tmp = Path(tempfile.mkdtemp(prefix="rp_roll_"))
src = ROOT / "发布版" / "classes"
if src.exists():
    shutil.copytree(src, tmp / "classes")
else:
    (tmp / "classes" / "默认班级").mkdir(parents=True)

from app.app_data import ClassManager
from app.ui_main import MainWindow

mgr = ClassManager(tmp)
mgr.ensure_dirs()
win = MainWindow(mgr)
win.setWindowTitle("ROLLING PAINT")
win.resize(1440, 900)
win.show()
win.startup()
app.processEvents()
for _ in range(80):
    app.processEvents()
    if win.store is not None:
        break
time.sleep(0.4)
app.processEvents()

counts = Counter()
areas = Counter()
rec = {"on": False}


class Tap(QObject):
    def eventFilter(self, obj, event):
        if rec["on"] and event.type() == QEvent.Paint:
            try:
                r = event.rect()
                name = obj.objectName() or type(obj).__name__
                counts[name] += 1
                areas[name] += max(0, r.width()) * max(0, r.height())
            except Exception:
                pass
        return False


tap = Tap()
app.installEventFilter(tap)

dp = win.draw_page
dp.start()
app.processEvents()
rec["on"] = True
t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.0:
    app.processEvents()
    time.sleep(0.002)
rec["on"] = False
dp.stop_silent()
app.processEvents()

print("滚动 1 秒内的 Paint 事件（按控件汇总）：")
for name, n in counts.most_common(15):
    print(f"  {name:24s} x{n:4d}  累计面积={areas[name]/1e6:8.2f} Mpx")

app.quit()
