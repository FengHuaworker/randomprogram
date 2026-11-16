# -*- coding: utf-8 -*-
"""入场动画帧序列：用**真实动画**的采样参数，把抽号页在各时刻的合成结果拼成
一条竖带，用来肉眼检查「是否发虚 / 是否被裁切 / 节奏是否合理」。

为什么不直接截图：win.grab() 会绕过 QGraphicsEffect（抓不到变换），
所以这里取未变换的源图，再按 MotionEffect.draw 的算法（含纯平移取整像素）
在测试进程里复算一遍。
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(Path(__file__).resolve().parents[1]))
theme.apply_theme(app)

from app.app_data import ClassManager
from tools._probe_env import temp_classes
from app.ui_main import MainWindow
from app.motion import MotionEffect, page_enter

mgr = ClassManager(temp_classes())
mgr.ensure_dirs()
win = MainWindow(mgr)
win.setWindowTitle("FILMSTRIP")
win.showMaximized()
win.startup()
for _ in range(200):
    app.processEvents()
    if win.store is not None:
        break
t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.5:
    app.processEvents()
    time.sleep(0.002)

page = win.draw_page
base = page.grab().toImage()          # 未变换的「源」（绕过 effect）
W, H = base.width(), base.height()

# ---- 跑真实入场动画，按 ~8ms 采样参数 ----
page_enter(page, dur=200, dy=8)
eff = page.graphicsEffect()
print("page effect:", type(eff).__name__)
if not isinstance(eff, MotionEffect):
    print("特效已被禁用/移除，无法采样")
    sys.exit(0)

samples = []
t0 = time.perf_counter()
while time.perf_counter() - t0 < 0.45:
    app.processEvents()
    samples.append((time.perf_counter() - t0, eff.s, eff.dx, eff.dy, eff.a))
    time.sleep(0.006)

# 取 8 个时间点（覆盖 0~200ms 与结束态）
DUR = 0.200
picks = []
for frac in (0.0, 0.06, 0.14, 0.26, 0.42, 0.62, 0.85, 1.0):
    target = DUR * frac
    best = min(samples, key=lambda r: abs(r[0] - target))
    picks.append((frac, best))

# ---- 按 MotionEffect.draw 的算法复算 ----
SC = 0.52
sw, sh = int(W * SC), int(H * SC)
strip = QImage(sw * 2, sh * 4, QImage.Format_ARGB32_Premultiplied)
strip.fill(QColor("#C9CDD4"))
BG = QColor("#F1F3F8")                # 与 COLORS['surface'] 一致

for i, (frac, (t, s, dx, dy, a)) in enumerate(picks):
    frame = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    frame.fill(BG)
    p = QPainter(frame)
    p.setOpacity(max(0.0, min(1.0, a)))
    if abs(s - 1.0) < 1e-4:
        # 纯平移：取整像素，不做任何重采样（与线上一致）
        p.drawImage(int(round(dx)), int(round(dy)), base)
        mode = "像素对齐"
    else:
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(W / 2.0 + dx, H / 2.0 + dy)
        p.scale(s, s)
        p.translate(-W / 2.0, -H / 2.0)
        p.drawImage(0, 0, base)
        mode = f"缩放{s:.3f}"
    p.end()

    cx, cy = (i % 2) * sw, (i // 2) * sh
    p2 = QPainter(strip)
    p2.drawImage(cx, cy, frame.scaled(sw, sh, Qt.IgnoreAspectRatio,
                                      Qt.SmoothTransformation))
    p2.setPen(QColor("#1A1C1E"))
    p2.drawText(cx + 8, cy + 18,
                f"{frac*100:.0f}%  t={t*1000:.0f}ms  a={a:.2f}  dy={dy:.1f}  {mode}")
    p2.end()

strip.save("ui_preview/enter_filmstrip.png")
print("saved ui_preview/enter_filmstrip.png")
