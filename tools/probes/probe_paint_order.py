# -*- coding: utf-8 -*-
"""判定：父控件带 MotionEffect 动画时，子控件的 Paint 事件何时发生？
若子 Paint 与父 draw 交错出现（属于 effect 子树渲染的一部分），则失效网络
必须忽略「effect 渲染期间的子树 Paint」，否则缓存永远命中不了。
用法：python tools/probe_paint_order.py
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QVariantAnimation, QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

app = QApplication(sys.argv)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.motion import MotionEffect

seq = []


class Tap(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Paint:
            seq.append((time.perf_counter(), "paint:" + type(obj).__name__))
        return False


tap = Tap()
app.installEventFilter(tap)

parent = QWidget()
parent.setFixedSize(400, 300)
parent.setStyleSheet("background:#DCE6F2;")
lay = QVBoxLayout(parent)
for i in range(5):
    lab = QLabel(f"line {i}")
    lab.setStyleSheet("font-size:16px;")
    lay.addWidget(lab)
parent.show()
app.processEvents()

eff = MotionEffect(parent)
parent.setGraphicsEffect(eff)

# 记录 draw 调用
_orig_draw = MotionEffect.draw


def timed_draw(self, painter):
    seq.append((time.perf_counter(), "DRAW"))
    return _orig_draw(self, painter)


MotionEffect.draw = timed_draw

done = {"v": False}
anim = QVariantAnimation()
anim.setStartValue(0.0)
anim.setEndValue(1.0)
anim.setDuration(300)
anim.valueChanged.connect(lambda v: eff.set_values(s=0.9 + 0.1 * float(v)))
anim.finished.connect(lambda: done.__setitem__("v", True))
anim.start()

t0 = time.perf_counter()
while not done["v"] and time.perf_counter() - t0 < 1.5:
    app.processEvents()
    time.sleep(0.001)

MotionEffect.draw = _orig_draw
app.processEvents()

# 分析交错模式：取一段连续事件看顺序
print("事件序列（前 40 条）：")
for t, name in seq[:40]:
    print(f"  {(t - seq[0][0])*1000:8.2f}ms  {name}")

draws = sum(1 for _, n in seq if n == "DRAW")
child_paints = sum(1 for _, n in seq if n.startswith("paint:") and n != "paint:QWidget")
parent_paints = sum(1 for _, n in seq if n == "paint:QWidget")
print(f"\nDRAW={draws}  父paint={parent_paints}  子paint={child_paints}")
