# -*- coding: utf-8 -*-
"""投影代价探针（不依赖主窗口）：对比带原生投影 / 无投影 / MotionEffect 合成的
单次渲染成本，用来判断「恢复卡片投影」是否会把滚动重绘拖慢。
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (QApplication, QFrame, QVBoxLayout, QLabel)

app = QApplication(sys.argv)
from app.motion import MotionEffect, _effect

IMG_W, IMG_H = 880, 560


def timeit(fn, n=15):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return ts[len(ts) // 2], ts[int(len(ts) * 0.9)]


def make_card():
    f = QFrame()
    f.resize(IMG_W, IMG_H)
    f.setStyleSheet("background:#FFFFFF; border-radius:28px;")
    v = QVBoxLayout(f)
    lab = QLabel("42")
    lab.setAlignment(Qt.AlignCenter)
    lab.setStyleSheet("background:transparent; color:#B03A2E; font-size:150px;")
    v.addWidget(lab)
    return f


def render(w):
    img = QImage(w.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    w.render(img)


card = make_card()
card.show()
app.processEvents()

med, p90 = timeit(lambda: render(card))
print(f"无投影        单次渲染 中位={med:6.2f}ms P90={p90:6.2f}ms")

from PySide6.QtWidgets import QGraphicsDropShadowEffect
sh = QGraphicsDropShadowEffect(card)
sh.setBlurRadius(26)
sh.setOffset(0, 8)
sh.setColor(QColor(0, 0, 0, 30))
card.setGraphicsEffect(sh)
app.processEvents()
med, p90 = timeit(lambda: render(card))
print(f"原生投影      单次渲染 中位={med:6.2f}ms P90={p90:6.2f}ms")

eff = _effect(card)          # 接管：备份投影 + 装 MotionEffect
app.processEvents()
eff.invalidate()
med, p90 = timeit(lambda: (eff.invalidate(), render(card)), 10)
print(f"MotionEffect  源重渲   中位={med:6.2f}ms P90={p90:6.2f}ms  (含阴影合成)")

img = QImage(card.size(), QImage.Format_ARGB32_Premultiplied)
eff.invalidate()
p = QPainter(img)
eff.draw(p)
p.end()


def one_draw():
    p = QPainter(img)
    eff.draw(p)
    p.end()


med, p90 = timeit(one_draw, 20)
print(f"MotionEffect  缓存帧   中位={med:6.2f}ms P90={p90:6.2f}ms  (阴影+源 两次 drawPixmap)")
print("done")
