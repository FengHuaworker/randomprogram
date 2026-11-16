# -*- coding: utf-8 -*-
"""对照实验：按钮在不同容器内渲染——定位 type=primary 失效的原因。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPushButton, QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QFontDatabase

app = QApplication([])
for f in ('tools/qtfonts/msyh.ttc', 'assets/fonts/PlayfairDisplay.ttf', 'assets/fonts/DMSans.ttf'):
    QFontDatabase.addApplicationFont(str(Path(r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker') / f))

from app import theme
from app.ui_widgets import DialogCard
theme.apply_theme(app)

root = QWidget()
root.resize(560, 380)
lay = QVBoxLayout(root)

card = DialogCard(root)
card_lay = QVBoxLayout(card)
card_lay.setContentsMargins(28, 26, 28, 16)

# 1) 直接放卡片内
b1 = QPushButton('A 卡片内-无局部样式')
b1.setProperty('type', 'primary')
b1.setFixedHeight(48)
card_lay.addWidget(b1)

# 2) 卡片内的 body（带局部 stylesheet，与向导 body 一致）
body = QWidget(card)
body.setStyleSheet('background: transparent;')
body_lay = QVBoxLayout(body)
body_lay.setContentsMargins(0, 4, 0, 0)
b2 = QPushButton('B body内-局部样式')
b2.setProperty('type', 'primary')
b2.setFixedHeight(48)
body_lay.addWidget(b2)
# body 内再加一个“扰流” QLabel（与向导 tip 类似）
tip = QLabel('名单格式：一行一个姓名……')
tip.setWordWrap(True)
tip.setStyleSheet('font-size:12px; color:#8C857B; background:transparent;')
body_lay.addWidget(tip)
card_lay.addWidget(body)

# 3) 卡片内 action-primary 对照
b3 = QPushButton('C 卡片内-action-primary')
b3.setProperty('mtype', 'action-primary')
b3.setFixedHeight(48)
card_lay.addWidget(b3)

lay.addWidget(card)
root.show()
app.processEvents()
root.grab().save(r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\ui_preview\probe_env.png')
print('saved probe_env')
