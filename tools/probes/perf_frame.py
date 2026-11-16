# -*- coding: utf-8 -*-
"""精确测量 MotionEffect 每帧 draw() 成本（含 sourcePixmap 重渲染子树）。
用法：python tools/perf_frame.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QVariantAnimation
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

import shutil
import tempfile

tmp = Path(tempfile.mkdtemp(prefix="rp_frame_"))
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
win.resize(1440, 860)
win.show()
app.processEvents()
for _ in range(50):
    app.processEvents()
    if win.store is not None:
        break

dp = win.draw_page
win.stack.setCurrentIndex(0)
dp.refresh()
dp._stretch_grid()
app.processEvents()

import app.motion as motion

# ---- 用计时包装测量每帧 draw 成本 ----
_orig_draw = motion.MotionEffect.draw
timings = {"list": [], "on": False}


def timed_draw(self, painter):
    if not timings["on"]:
        return _orig_draw(self, painter)
    t0 = time.perf_counter()
    try:
        return _orig_draw(self, painter)
    finally:
        timings["list"].append((time.perf_counter() - t0) * 1000.0)


motion.MotionEffect.draw = timed_draw


def measure(widget, name, dur=500):
    timings["list"].clear()
    timings["on"] = True
    done = {"v": False}
    eff = widget.graphicsEffect()
    anim = QVariantAnimation()
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(dur)
    # 与真实 animate() 一致：只改效果参数，不 widget.update()
    anim.valueChanged.connect(lambda v: eff.set_values(
        s=0.9 + 0.1 * float(v), dy=10.0 * (1.0 - float(v))))
    anim.finished.connect(lambda: done.__setitem__("v", True))
    anim.start()
    t0 = time.perf_counter()
    while not done["v"] and time.perf_counter() - t0 < dur / 1000 + 2:
        app.processEvents()
        time.sleep(0.001)
    timings["on"] = False
    app.processEvents()
    ts = timings["list"]
    if ts:
        ts.sort()
        print(f"{name:28s} draw次数={len(ts):3d}  "
              f"中位={ts[len(ts)//2]:6.2f}ms  P90={ts[int(len(ts)*0.9)]:6.2f}ms  "
              f"最大={ts[-1]:6.2f}ms  合计={sum(ts):7.1f}ms")
    else:
        print(f"{name:28s} 无 draw 调用")


# 让 widget 带上 MotionEffect（复用 _effect 私有逻辑）
def attach(w):
    eff = w.graphicsEffect()
    if not isinstance(eff, motion.MotionEffect):
        eff = motion.MotionEffect(w)
        w.setGraphicsEffect(eff)
    return eff


for w, name in ((dp, "整页(page)"), (dp.hero, "hero主卡片"),
                (dp.rail, "rail右栏"), (dp.batch_card, "batch批量卡"),
                (dp.num_label, "num_label大数字")):
    attach(w)
    measure(w, name)

# ---- 对照组：普通 QLabel 文字动画（无 effect）----
from PySide6.QtWidgets import QLabel

lab = QLabel("42")
lab.setFixedSize(400, 200)
lab.setStyleSheet("font-size:150px;")
lab.show()
app.processEvents()
timings["list"].clear()
timings["on"] = True
done = {"v": False}
anim = QVariantAnimation()
anim.setStartValue(0.0)
anim.setEndValue(1.0)
anim.setDuration(500)
anim.valueChanged.connect(lambda v: lab.update())
anim.finished.connect(lambda: done.__setitem__("v", True))
anim.start()
t0 = time.perf_counter()
while not done["v"] and time.perf_counter() - t0 < 2:
    app.processEvents()
    time.sleep(0.001)
timings["on"] = False
ts = timings["list"]
if ts:
    ts.sort()
    print(f"{'对照:普通QLabel重绘':28s} paint次数={len(ts):3d}  "
          f"中位={ts[len(ts)//2]:6.2f}ms")
