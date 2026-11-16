# -*- coding: utf-8 -*-
"""离屏成本探针：投影 / 整页入场特效 的每帧绘制代价。

前台合成器不可用时（无 Paint 事件），用 QWidget.render() 到 QImage 测真实
绘制耗时——包含子控件与 QGraphicsEffect 的源渲染。
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

tmp = Path(tempfile.mkdtemp(prefix="rp_perf_"))
src = ROOT / "发布版" / "classes"
if src.exists():
    shutil.copytree(src, tmp / "classes")

from app.app_data import ClassManager
from app.ui_main import MainWindow

mgr = ClassManager(tmp)
mgr.ensure_dirs()
win = MainWindow(mgr)
win.resize(1500, 940)
win.show()
win.startup()
for _ in range(120):
    app.processEvents()
    if win.store is not None:
        break
win.resize(1500, 940)
app.processEvents()
time.sleep(0.5)
app.processEvents()
# 等入场动画结束
t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.4:
    app.processEvents()
    time.sleep(0.002)


def timeit(fn, n=18):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return ts[len(ts) // 2], ts[int(len(ts) * 0.9)]


def render_widget(w):
    img = QImage(w.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    w.render(p)
    p.end()
    return img


hero = win.draw_page.hero
page = win.draw_page
print("hero effect:", type(hero.graphicsEffect()).__name__)

med, p90 = timeit(lambda: render_widget(hero))
print(f"hero 单次渲染       中位={med:6.2f}ms P90={p90:6.2f}ms  (含原生投影)")

med, p90 = timeit(lambda: render_widget(page))
print(f"整页单次渲染        中位={med:6.2f}ms P90={p90:6.2f}ms  (无特效)")

# 整页入场特效每帧成本：draw() 只用缓存 + drawPixmap
from app.motion import MotionEffect, animate
eff = page.graphicsEffect()
print("page effect:", type(eff).__name__)
if isinstance(eff, MotionEffect):
    eff.setEnabled(True)
    eff.invalidate()
    img = QImage(page.size(), QImage.Format_ARGB32_Premultiplied)
    for i in range(6):
        eff.set_values(a=0.2 + 0.1 * i, dy=20 - 3 * i, s=0.994 + 0.001 * i)
        p = QPainter(img)
        p.setClipRect(img.rect())
        eff.draw(p)
        p.end()

    # 直接给 draw() 计时（稳定态：缓存命中）
    def one_draw():
        p = QPainter(img)
        eff.draw(p)
        p.end()

    med, p90 = timeit(one_draw, 30)
    print(f"整页效果 draw()     中位={med:6.2f}ms P90={p90:6.2f}ms  (缓存命中)")

    def invalidate_and_render():
        eff.invalidate()
        render_widget(page)

    med, p90 = timeit(invalidate_and_render, 8)
    print(f"源失效后重渲一帧    中位={med:6.2f}ms P90={p90:6.2f}ms  (含阴影模糊)")

print("done")
