# -*- coding: utf-8 -*-
"""真实窗口逐一驱动全部应用内弹窗：验证入场/内部过渡/关闭动画不崩、能正常返回。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app.app_data as ad
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ad.get_base_dir = lambda: (ROOT / "发布版")
PREVIEW = ROOT / "ui_preview"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)
from app.ui_main import MainWindow
from app.ui_widgets import MaterialAlert, AppFilePickerDialog
from app.ui_dialogs import (ClassNameDialog, SetupWizard, RosterEditorDialog,
                            StudentPickDialog, AppSettingsDialog,
                            AdminPasswordDialog, HistoryCleanupDialog)

win = MainWindow(ad.ClassManager())
win.resize(1100, 760)
win.show()
win.startup()
store = win.store
cfg = store.load_config()
students = store.get_students(cfg)

LOG = []


def snap(dlg, name):
    try:
        dlg.grab().save(str(PREVIEW / f"_dlg_{name}.png"))
    except Exception as e:
        LOG.append(f"{name}: snapshot FAIL {e}")


# 每个用例：(名称, 构造, 交互函数, 关闭方式)
def make_cases():
    return [
        ("alert", lambda: MaterialAlert(win, "动画验收", "这是一个应用内提醒弹窗",
                                        buttons=[("知道了", True)]), None, "accept"),
        ("classname", lambda: ClassNameDialog(win, "新建班级", "测试"), None, "reject"),
        ("admin", lambda: AdminPasswordDialog(win),
         lambda d: (d.edit.setText("wrong-pass"), d._check()), "reject"),
        ("wizard", lambda: SetupWizard(win, store, dict(cfg)),
         lambda d: (d.card_simple.set_selected(True), d._select_mode("simple", True),
                    d._next()), "reject"),
        ("studentpick", lambda: StudentPickDialog(win, "屏蔽学生", students, set()),
         lambda d: (d.search.setText("陈"), d._set_all(Qt.Checked)), "reject"),
        ("roster", lambda: RosterEditorDialog(win, store),
         lambda d: (d._add(), d._del(), d._sync_count()), "reject"),
        ("settings", lambda: AppSettingsDialog(win, store, dict(cfg)),
         lambda d: d.sw_anti.setChecked(not d.sw_anti.isChecked()), "reject"),
        ("cleanup", lambda: HistoryCleanupDialog(win, store),
         lambda d: d._use_preset("7d"), "reject"),
        ("filepicker", lambda: AppFilePickerDialog(win, "选择名单", start_dir=str(ROOT)),
         None, "reject"),
    ]


cases = make_cases()
idx = {"i": 0}


def run_next():
    if idx["i"] >= len(cases):
        print("ALL DIALOGS DONE", flush=True)
        for line in LOG:
            print(line, flush=True)
        app.quit()
        return
    name, ctor, action, how = cases[idx["i"]]
    idx["i"] += 1
    try:
        dlg = ctor()
    except Exception as e:
        LOG.append(f"{name}: CONSTRUCT FAIL {e!r}")
        QTimer.singleShot(0, run_next)
        return

    def on_show():
        snap(dlg, name)
        if action:
            try:
                action(dlg)
            except Exception as e:
                LOG.append(f"{name}: ACTION FAIL {e!r}")

    def on_close():
        try:
            if how == "accept":
                dlg.accept()
            else:
                dlg.reject()
        except Exception as e:
            LOG.append(f"{name}: CLOSE FAIL {e!r}")

    def on_timeout():
        # 关闭动画若卡住，强制结束并记为失败
        LOG.append(f"{name}: !!! CLOSE TIMEOUT (exec 未返回)")
        try:
            dlg.done(0)
        except Exception:
            pass
        app.quit()

    timer = QTimer(win)
    timer.setSingleShot(True)
    timer.timeout.connect(on_timeout)
    timer.start(4000)
    QTimer.singleShot(450, on_show)
    QTimer.singleShot(1000, on_close)
    rc = dlg.exec()
    timer.stop()
    LOG.append(f"{name}: exec returned {rc}")
    print(f"{name}: exec returned {rc}", flush=True)
    QTimer.singleShot(80, run_next)


QTimer.singleShot(600, run_next)
QTimer.singleShot(60000, app.quit)
app.exec()
print("dialog motion test finished", flush=True)
