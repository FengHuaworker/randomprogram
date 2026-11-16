# -*- coding: utf-8 -*-
"""验证：app 级事件过滤器能否收到「子树内任意控件 update()」的 UpdateRequest。
这决定 MotionEffect 源码位图缓存的安全失效策略。
用法：python tools/probe_update_event.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

app = QApplication(sys.argv)

seen = {"self": 0, "child": 0, "grandchild": 0, "sibling": 0, "other": 0}


class Tracker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.UpdateRequest:
            w = obj if isinstance(obj, QWidget) else None
            name = getattr(w, "_probe_name", None)
            if name:
                seen[name] = seen.get(name, 0) + 1
        return False


tracker = Tracker()
app.installEventFilter(tracker)

root = QWidget()
root._probe_name = "self"
root.resize(400, 300)
lay = QVBoxLayout(root)
child = QLabel("child")
child._probe_name = "child"
lay.addWidget(child)
mid = QWidget()
mid._probe_name = None
lay.addWidget(mid)
gl = QVBoxLayout(mid)
gc = QLabel("grandchild")
gc._probe_name = "grandchild"
gl.addWidget(gc)
root.show()
app.processEvents()

sibling = QLabel("sibling")
sibling._probe_name = "sibling"
sibling.show()
app.processEvents()

print("--- child.update() x5 ---")
for _ in range(5):
    child.update()
app.processEvents()
print(dict(seen))
print("--- grandchild.update() x5 ---")
for _ in range(5):
    gc.update()
app.processEvents()
print(dict(seen))
print("--- sibling.update() x5 ---")
for _ in range(5):
    sibling.update()
app.processEvents()
print(dict(seen))
