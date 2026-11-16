# -*- coding: utf-8 -*-
"""隔离测试：独立 primary 按钮是否正常渲染。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QFontDatabase

app = QApplication([])
for f in ('tools/qtfonts/msyh.ttc', 'assets/fonts/PlayfairDisplay.ttf', 'assets/fonts/DMSans.ttf'):
    QFontDatabase.addApplicationFont(str(Path(r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker') / f))

from app import theme
theme.apply_theme(app)

b = QPushButton('测试主按钮')
b.setProperty('type', 'primary')
b.resize(200, 48)
b.show()
app.processEvents()
b.grab().save(r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\ui_preview\probe_standalone_primary.png')
qss = app.styleSheet()
sel = 'QPushButton[type="primary"]'
print('SELECTOR_PRESENT', sel in qss, '| QSS_LEN', len(qss), '| ENABLED', b.isEnabled())
