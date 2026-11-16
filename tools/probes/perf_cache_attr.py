# -*- coding: utf-8 -*-
"""缓存失效归因：找出动画期间到底是谁在失效 MotionEffect 缓存。
分三组测量：①仅整页有效果 ②仅hero有效果 ③页+hero嵌套。
用法：python tools/perf_cache_attr.py
"""
import os
import shutil
import sys
import tempfile
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

tmp = Path(tempfile.mkdtemp(prefix="rp_attr_"))
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
win.startup()
app.processEvents()
for _ in range(80):
    app.processEvents()
    if win.store is not None:
        break
dp = win.draw_page
win.stack.setCurrentIndex(0)
dp.refresh()
dp._stretch_grid()
app.processEvents()

import app.motion as motion

# ---- 给 tap 打点：记录每次失效的 (目标类名, 是否自身) ----
TAP = motion._TAP
_orig_ef = TAP.eventFilter
attr = {"on": False, "self_hits": 0, "desc_hits": 0, "ext_hits": 0, "names": {}}


def tapped(obj, event):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QWidget
    if event.type() != QEvent.Paint:
        return _orig_ef(obj, event)
    if attr["on"]:
        w = obj if isinstance(obj, QWidget) else None
        if w is not None:
            eff = w.graphicsEffect()
            if isinstance(eff, motion.MotionEffect):
                if getattr(eff, "_own_paint", False):
                    eff._own_paint = False
                    attr["self_hits"] += 1
                else:
                    attr["ext_hits"] += 1
                    attr["names"][type(w).__name__] = attr["names"].get(type(w).__name__, 0) + 1
                    eff.invalidate()
            p = w.parentWidget()
            while p is not None:
                pe = p.graphicsEffect()
                if isinstance(pe, motion.MotionEffect):
                    attr["desc_hits"] += 1
                    attr["names"]["→" + type(p).__name__] = attr["names"].get("→" + type(p).__name__, 0) + 1
                    pe.invalidate()
                p = p.parentWidget()
    return _orig_ef(obj, event)


TAP.eventFilter = tapped

# ---- 计时 draw ----
_orig_draw = motion.MotionEffect.draw
timings = {"list": [], "on": False}


def timed_draw(self, painter):
    if not timings["on"]:
        return _orig_draw(self, painter)
    t0 = time.perf_counter()
    try:
        return _orig_draw(self, painter)
    finally:
        timings["list"].append((time.perf_counter() - t0) * 1000)


motion.MotionEffect.draw = timed_draw


def attach(w):
    eff = w.graphicsEffect()
    if not isinstance(eff, motion.MotionEffect):
        eff = motion.MotionEffect(w)
        w.setGraphicsEffect(eff)
    return eff


def measure(name, widget, dur=500):
    eff = attach(widget)
    eff.invalidate()
    attr.update({"on": True, "self_hits": 0, "desc_hits": 0, "ext_hits": 0, "names": {}})
    timings["list"].clear()
    timings["on"] = True
    done = {"v": False}
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
    attr["on"] = False
    app.processEvents()
    ts = sorted(timings["list"])
    med = ts[len(ts) // 2] if ts else 0
    p90 = ts[int(len(ts) * 0.9)] if ts else 0
    print(f"{name:22s} draw={len(ts):3d} 中位={med:6.2f}ms P90={p90:6.2f}ms "
          f"合计={sum(ts):7.1f}ms | 自身失效={attr['ext_hits']:3d} "
          f"祖先连累={attr['desc_hits']:3d} "
          f"{attr['names']}")


print("== ① 仅整页有效果 ==")
measure("整页", dp)
dp.setGraphicsEffect(None)

print("== ② 仅 hero 有效果 ==")
measure("hero", dp.hero)
dp.hero.setGraphicsEffect(None)

print("== ③ 页 + hero 嵌套 ==")
measure("嵌套-整页", dp)
measure("嵌套-hero", dp.hero)
dp.setGraphicsEffect(None)
dp.hero.setGraphicsEffect(None)

print("== ④ rail 右栏（内含两个 QListWidget） ==")
measure("rail", dp.rail)
dp.rail.setGraphicsEffect(None)
