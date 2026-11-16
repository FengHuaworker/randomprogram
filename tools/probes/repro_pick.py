# -*- coding: utf-8 -*-
"""复现：点击「添加到长期屏蔽」无反应。"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

app = QApplication([])
for f in ('tools/qtfonts/msyh.ttc', 'assets/fonts/PlayfairDisplay.ttf', 'assets/fonts/DMSans.ttf'):
    QFontDatabase.addApplicationFont(str(Path(r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker') / f))

from app import theme
theme.apply_theme(app)
from app.app_data import ClassManager, MODE_ADVANCED
from app.ui_main import MainWindow
from app.ui_dialogs import StudentPickDialog
from app.ui_widgets import MaterialDialog

tmp = Path(tempfile.mkdtemp())
mgr = ClassManager(tmp)
mgr.ensure_dirs()
n = mgr.create_class('测试班')
st = mgr.get_class(n)
st.roster_write(['张三', '李四', '王五', '赵六'])
cfg = st.load_config()
cfg['mode'] = MODE_ADVANCED
cfg['total_count'] = 4
st.save_config(cfg)

win = MainWindow(mgr)
win.resize(1280, 800)
win.show()
app.processEvents()
win._reload_class(n)
app.processEvents()

# 1) 直接构造测试
students = st.get_students(cfg)
dlg = StudentPickDialog(win.shield_page, '选择要长期屏蔽的学生', students, set())
print('DLG built. body children:', [type(c).__name__ for c in dlg.body.children()][:6])
print('listw count before fill?', dlg.listw.count())
QTimer.singleShot(600, dlg.reject)
r = dlg.exec()
print('EXEC returned:', r, '| open flag:', dlg.isVisible())
print('grab check:', dlg.grab().size())

# 2) 点击按钮路径：给 exec 挂自动关闭
def auto_close():
    # 找到屏蔽页当前打开的 dlg（父窗口 children 无法枚举，直接再模拟按钮点击并定时关闭）
    pass

QTimer.singleShot(700, lambda: None)
print('DONE')
shutil.rmtree(tmp, ignore_errors=True)
