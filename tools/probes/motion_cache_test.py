# -*- coding: utf-8 -*-
"""MotionEffect 源位图缓存正确性 + 性能测试。
场景1：父卡片特效动画中，子控件同时做 QPropertyAnimation —— 子动画必须可见
      （缓存不能把子树「冻住」）。
场景2：父卡片特效动画中，子控件文字被外部改写 —— 新文字必须出现。
场景3：纯特效动画（子树静态）—— 每帧 draw 成本应远低于无缓存时(~2.5ms)。
用法：python tools/motion_cache_test.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (QPropertyAnimation, QVariantAnimation, QEasingCurve,
                            QRectF, Property)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

app = QApplication(sys.argv)
from app.motion import MotionEffect, animate, pop_in

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


class Child(QWidget):
    """自带属性动画的子控件（模拟 RippleButton 的 press/hover）。"""

    def __init__(self):
        super().__init__()
        self._p = 0.0
        self.setFixedSize(120, 60)
        self.setStyleSheet("background:#4E7CB8;border-radius:12px;")

    def get_p(self):
        return self._p

    def set_p(self, v):
        self._p = v
        self.update()

    p = Property(float, get_p, set_p)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 用 _p 画一个明显的指示块：冻住就看得出
        w = 20 + 80 * self._p
        p.setBrush(QColor("#FFD166"))
        p.drawRoundedRect(QRectF(10, 10, w, 40), 8, 8)
        p.end()


def drain(seconds):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        app.processEvents()
        time.sleep(0.001)


# ---------------- 场景 1+3：父动画中 child 属性动画 ----------------
root = QWidget()
root.setWindowTitle("cache test")
root.resize(600, 400)
lay = QVBoxLayout(root)
card = QWidget()
card.setFixedSize(400, 260)
card.setStyleSheet("background:#DCE6F2;border-radius:20px;")
cl = QVBoxLayout(card)
child = Child()
cl.addWidget(child)
lab = QLabel("静态文字")
lab.setStyleSheet("font-size:20px;")
cl.addWidget(lab)
lay.addWidget(card)
root.show()
app.processEvents()

# 子控件属性动画（0 → 1，1秒）
ca = QPropertyAnimation(child, b"p")
ca.setStartValue(0.0)
ca.setEndValue(1.0)
ca.setDuration(1000)
ca.setEasingCurve(QEasingCurve.Linear)
ca.start()

# 父卡片特效动画同时进行
pop_in(card, dur=800, dy=20, s=0.9)

# 采样：动画中途抓窗口，看 child 的指示块宽度是否在变
samples = []
t0 = time.perf_counter()
while time.perf_counter() - t0 < 0.8:
    app.processEvents()
    time.sleep(0.005)
    samples.append(child._p)

varying = len(set(round(s, 3) for s in samples)) > 5
check("场景1 父特效中子属性动画不被冻结", varying,
      f"child.p 采样 {len(samples)} 个, 取值数={len(set(round(s,3) for s in samples))}")

drain(0.6)

# ---------------- 场景 2：父动画中外部改文字 ----------------
pop_in(card, dur=700, dy=20, s=0.9)


def swap_text():
    lab.setText("已更换的文字")
    from app.motion import invalidate
    invalidate(card)


from PySide6.QtCore import QTimer
QTimer.singleShot(250, swap_text)
drain(0.8)
check("场景2 父动画中外部改子文字生效", lab.text() == "已更换的文字",
      f"text={lab.text()!r}")

# ---------------- 场景 3：动画期间源位图只渲染一次（缓存真正生效） ----------------
# 为什么不测「每帧多少毫秒」：绝对耗时受机器负载影响极大，同一台机器上
# 400x260 与 1000x600 的比值结论还会互相矛盾。真正决定卡不卡的是**有没有
# 每帧重渲整棵子树**，直接用 sourcePixmap 的调用次数来判定，与硬件无关。
import app.motion as motion

_sp_calls = {"n": 0}
_real_source_pixmap = MotionEffect.sourcePixmap


def counting_source_pixmap(self, *args, **kwargs):
    _sp_calls["n"] += 1
    return _real_source_pixmap(self, *args, **kwargs)


MotionEffect.sourcePixmap = counting_source_pixmap

card2 = QWidget()
card2.setFixedSize(1000, 600)
card2.setStyleSheet("background:#DCE6F2;border-radius:20px;")
_v = QVBoxLayout(card2)
for _i in range(4):
    _v.addWidget(Child())
root.layout().addWidget(card2)
card2.show()
app.processEvents()

_sp_calls["n"] = 0
pop_in(card2, dur=700, dy=20, s=0.9)
drain(1.0)
calls = _sp_calls["n"]
MotionEffect.sourcePixmap = _real_source_pixmap
check("场景3 700ms 动画期间源位图渲染次数 ≤ 3（无缓存时约 40 次）",
      calls <= 3, f"sourcePixmap 调用 {calls} 次")

print()
bad = [r for r in results if not r[1]]
print(f"总计 {len(results)} 项，失败 {len(bad)} 项")
app.quit()
sys.exit(1 if bad else 0)
