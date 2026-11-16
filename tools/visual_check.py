# -*- coding: utf-8 -*-
"""真实窗口自截图验证：切页 stagger / 滚动 / 定格弹跳 + 舞台光环。
用 widget.grab() 自截图（不依赖外部抓屏）。用法：python tools/visual_check.py
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

tmp = Path(tempfile.mkdtemp(prefix="rp_vis_"))
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
win.setWindowTitle("VISUAL CHECK")
win.resize(1440, 900)
win.show()
win.startup()
app.processEvents()
for _ in range(80):
    app.processEvents()
    if win.store is not None:
        break
time.sleep(0.5)
app.processEvents()

P = ROOT / "ui_preview"
dp = win.draw_page


def shot(name):
    img = win.grab()
    img.save(str(P / name))
    print("saved", name, img.width(), "x", img.height(), flush=True)


def wait(ms):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < ms / 1000:
        app.processEvents()
        time.sleep(0.002)


# 1) 切到统计页再切回抽号页（触发 stagger）
win._on_nav_changed(2)
wait(400)
win._on_nav_changed(0)
wait(140)          # stagger 进行中
shot("vc_stagger_mid.png")
wait(700)
shot("vc_stagger_end.png")

# 2) 开始抽号 → 滚动中
dp.start()
app.processEvents()
wait(500)
shot("vc_rolling.png")

# 3) 停止 → 定格弹跳 + 光环
dp.stop()
wait(420)          # bounce 峰值附近（+300ms 触发）
shot("vc_settle_bounce.png")
wait(500)
shot("vc_settle_halo.png")
wait(700)
shot("vc_settle_end.png")

# 4) 批量抽号弹层
dp.batch_draw()
wait(600)
shot("vc_batch.png")

print("done, tmp:", tmp)
app.quit()
