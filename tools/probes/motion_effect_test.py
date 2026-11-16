# -*- coding: utf-8 -*-
"""用屏幕抓拍验证 MotionEffect 的真实合成（widget.grab 会绕过 effect）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "ui_preview"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                               QVBoxLayout)
from PIL import ImageGrab
from app.motion import MotionEffect, pop_in

app = QApplication(sys.argv)
root = QWidget()
root.setWindowTitle("MotionFX")
root.setFixedSize(560, 420)
root.setStyleSheet("background:#FFFFFF;")
outer = QVBoxLayout(root)
outer.setContentsMargins(60, 50, 60, 50)

card = QWidget()
card.setFixedSize(420, 300)
card.setStyleSheet("background:#DCE6F2; border-radius:20px;")
lay = QVBoxLayout(card)
lay.setContentsMargins(30, 30, 30, 30)
title = QLabel("弹性动效验收")
title.setStyleSheet("font-size:24px; color:#2B3A4A;")
lay.addWidget(title)
body = QLabel("这段文字和按钮应当随卡片一起缩放、位移、淡入")
body.setWordWrap(True)
body.setStyleSheet("font-size:14px; color:#5A6B7C;")
lay.addWidget(body)
btn = QPushButton("开始")
btn.setStyleSheet("QPushButton{background:#4E7CB8;color:white;border:none;"
                  "border-radius:12px;padding:12px;font-size:15px;}")
lay.addWidget(btn)
lay.addStretch(1)
outer.addWidget(card)
root.show()
root.raise_()
app.processEvents()
import ctypes
_u = ctypes.windll.user32
_hwnd = int(root.winId())
_u.SetWindowPos(_hwnd, -1, 120, 90, 560, 420, 0x40)  # HWND_TOPMOST
_u.SetForegroundWindow(_hwnd)
app.processEvents()


def shot(name):
    r = root.frameGeometry()
    img = ImageGrab.grab(bbox=(r.left(), r.top(), r.right(), r.bottom()))
    img.save(str(P / name))
    print(name, img.size, flush=True)


def t1():
    eff = MotionEffect(card)
    card.setGraphicsEffect(eff)
    eff.set_values(s=0.86, dy=28, a=0.7)
    app.processEvents()
    QTimer.singleShot(150, lambda: shot("_fx_static.png"))
    QTimer.singleShot(300, t2)


def t2():
    card.setGraphicsEffect(None)
    pop_in(card, dur=900, dy=34, s=0.85)
    QTimer.singleShot(220, lambda: shot("_fx_mid.png"))
    QTimer.singleShot(1100, lambda: shot("_fx_end.png"))
    QTimer.singleShot(1300, app.quit)


QTimer.singleShot(300, t1)
QTimer.singleShot(4000, app.quit)
app.exec()
