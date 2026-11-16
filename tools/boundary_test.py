# -*- coding: utf-8 -*-
"""边界验收：弹跳过冲各时刻卡片四边/圆角是否完整、有无越界裁切。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "ui_preview"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                               QPushButton)
from PIL import ImageGrab
from app.motion import pop_in, bounce

app = QApplication(sys.argv)
root = QWidget()
root.setWindowTitle("BoundaryFX")
root.setFixedSize(600, 460)
root.setStyleSheet("background:#FFFFFF;")
outer = QVBoxLayout(root)
outer.setContentsMargins(80, 70, 80, 70)

card = QWidget()
card.setFixedSize(420, 300)
card.setStyleSheet("background:#DDE7F3; border:3px solid #4E7CB8; border-radius:22px;")
lay = QVBoxLayout(card)
lay.setContentsMargins(26, 22, 26, 22)
lab = QLabel("边界验收 · 圆角与边框")
lab.setStyleSheet("font-size:20px; color:#23384F;")
lay.addWidget(lab)
tip = QLabel("弹跳过冲时四边应始终完整，不应出现直边切平")
tip.setWordWrap(True)
tip.setStyleSheet("font-size:13px; color:#5A6B7C;")
lay.addWidget(tip)
btn = QPushButton("按钮")
btn.setStyleSheet("QPushButton{background:#4E7CB8;color:white;border:none;"
                  "border-radius:10px;padding:10px;}")
lay.addWidget(btn)
lay.addStretch(1)
outer.addWidget(card)
root.show()
app.processEvents()

import ctypes
_u = ctypes.windll.user32
_hwnd = int(root.winId())
_u.SetWindowPos(_hwnd, -1, 120, 90, 600, 460, 0x40)
_u.SetForegroundWindow(_hwnd)
app.processEvents()


def shot(name):
    r = root.frameGeometry()
    ImageGrab.grab(bbox=(r.left(), r.top(), r.right(), r.bottom())).save(str(P / name))
    print(name, flush=True)


def seq():
    pop_in(card, dur=900, dy=44, s=0.80)
    QTimer.singleShot(90, lambda: shot("_bd_090.png"))   # 起点：最大位移
    QTimer.singleShot(320, lambda: shot("_bd_320.png"))  # 弹簧过冲
    QTimer.singleShot(560, lambda: shot("_bd_560.png"))  # 回落
    QTimer.singleShot(1050, lambda: shot("_bd_end.png")) # 结束
    QTimer.singleShot(1150, lambda: bounce(card, s=1.24, dur=520, rot=-2.0))
    QTimer.singleShot(1260, lambda: shot("_bd_bounce.png"))
    QTimer.singleShot(1900, app.quit)


QTimer.singleShot(300, seq)
QTimer.singleShot(4000, app.quit)
app.exec()
