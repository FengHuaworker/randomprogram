# -*- coding: utf-8 -*-
"""
开发用预览脚本：offscreen 渲染主界面 / 启动标识 / 弹窗截图，检查视觉与动效。
用法：python tools/preview.py
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", str(Path(__file__).resolve().parent / "qtfonts"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402

from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402
from app.ui_dialogs import SetupWizard, RosterEditorDialog  # noqa: E402
from app.ui_widgets import SplashWindow, snack  # noqa: E402

OUT = ROOT / "ui_preview"
OUT.mkdir(exist_ok=True)


def register_dev_fonts():
    """offscreen 平台取不到系统字体：注册自带字体（雅黑 + 打包字体）。"""
    QtFonts = ROOT / "tools" / "qtfonts"
    for f in ("msyh.ttc",):
        p = QtFonts / f
        if p.exists():
            QFontDatabase.addApplicationFont(str(p))
    for f in ("PlayfairDisplay.ttf", "DMSans.ttf"):
        p = ROOT / "assets" / "fonts" / f
        if p.exists():
            QFontDatabase.addApplicationFont(str(p))


def save(win, name):
    win.grab().save(str(OUT / f"{name}.png"))
    print("saved:", name)


def main():
    app = QApplication(sys.argv)
    register_dev_fonts()
    theme.apply_theme(app)
    tmp = Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        # ---------- 0) 启动标识：呼吸动画 ----------
        splash = SplashWindow()
        splash.show_breath()
        app.processEvents()
        QTimer.singleShot(900, lambda: save(splash, "splash_breathe"))

        mgr = ClassManager(tmp)
        mgr.ensure_dirs()
        mgr.ensure_template()
        n = mgr.create_class("三年级1班")
        st = mgr.get_class(n)
        st.roster_write(["王小明", "李小华", "张小强", "陈雨桐", "刘一诺",
                         "赵子豪", "孙悦", "周天翔", "吴思彤", "郑浩然",
                         "冯晨曦", "褚俊杰"])
        cfg = st.load_config()
        cfg["mode"] = MODE_ADVANCED
        cfg["total_count"] = 12
        st.save_config(cfg)
        st.set_long_exempt([1, 2])
        st.set_short_exempt([3])

        win = MainWindow(mgr)
        win.resize(1280, 800)
        win.show()
        app.processEvents()
        win.nav.setCurrentIndex(0)
        win._reload_class(n)
        app.processEvents()

        # 1) 入场动画进行中（约 250ms）
        QTimer.singleShot(240, lambda: save(win, "anim_entrance"))
        # 2) 滚动抽号（光晕 + 微脉冲）
        QTimer.singleShot(700, lambda: (win.draw_page.start(),
                                        QTimer.singleShot(260, lambda: save(win, "anim_rolling"))))
        # 3) 定格（闪光 + 弹性放大 + 本轮高亮）
        QTimer.singleShot(1300, lambda: (win.draw_page.stop(),
                                         QTimer.singleShot(240, lambda: save(win, "anim_freeze"))))
        # 4) 稳定态
        QTimer.singleShot(2300, lambda: save(win, "main_window"))
        # 4.5) 底部信息卡（纸面卡 + 状态圆点）
        QTimer.singleShot(2600, lambda: (snack(win, "记录已导出 → exports\\三年级1班_记录_20260904.txt",
                                               kind="success"),
                                         QTimer.singleShot(350, lambda: save(win, "snackbar"))))

        # 配置展示页（视差色块 + 衬线标题）
        def snap_config():
            win.nav.setCurrentIndex(3)
            win.stack.setCurrentWidget(win.config_page)
            win.config_page.refresh()
            QTimer.singleShot(800, lambda: save(win, "config_page"))
        QTimer.singleShot(3800, snap_config)

        # 屏蔽管理页
        def snap_shield():
            win.nav.setCurrentIndex(4)
            win.shield_page.refresh()
            QTimer.singleShot(600, lambda: save(win, "shield_page"))
        QTimer.singleShot(5000, snap_shield)

        # 设置弹窗（语言 / 向导入口 / 防重）
        from app.ui_dialogs import AppSettingsDialog
        set_dlg = AppSettingsDialog(win, win.store, win.cfg)
        set_dlg.show()
        QTimer.singleShot(6400, lambda: save(set_dlg, "settings_dialog"))

        # 英文界面（语言即时切换）
        QTimer.singleShot(7100, lambda: (win.apply_lang("en"),
                                         QTimer.singleShot(500, lambda: save(win, "en_main"))))

        # 弹窗：配置向导
        wiz = SetupWizard(win, st, cfg)
        wiz.resize(620, 560)
        wiz.show()
        QTimer.singleShot(600, lambda: save(wiz, "wizard_step1"))

        # 向导：高级模式选中
        def snap_wiz_adv():
            wiz.card_advanced.set_selected(True)
            QTimer.singleShot(300, lambda: save(wiz, "wizard_adv"))
        QTimer.singleShot(1400, snap_wiz_adv)

        # 向导：走到第 3 步（上传名单），检查按钮与背景
        def snap_wiz_roster():
            wiz._state = "count"
            wiz._refresh()
            wiz._state = "roster"
            wiz._refresh()
            QTimer.singleShot(300, lambda: save(wiz, "wizard_roster"))
        QTimer.singleShot(2200, snap_wiz_roster)

        # 应用内文件选择器（选择班级名单文件）
        from app.ui_widgets import AppFilePickerDialog
        fp = AppFilePickerDialog(wiz, "选择班级名单文件", start_dir=ROOT, suffixes=(".txt",))
        fp.show()
        QTimer.singleShot(3000, lambda: save(fp, "file_picker"))

        # 名单编辑器（应用内弹窗 + 偏移装饰线）
        ed = RosterEditorDialog(win, st)
        ed.resize(560, 560)
        ed.show()
        QTimer.singleShot(600, lambda: save(ed, "roster_editor"))

        # 确认弹窗样式
        from app.ui_widgets import MaterialAlert
        alert = MaterialAlert(win, "重置本轮", "确定要重置本轮吗？将清空本轮已抽 3 人。",
                              buttons=[("取消", False), ("重置", True)])
        alert.show()
        QTimer.singleShot(1500, lambda: save(alert, "dialog_confirm"))

        # 等所有截图完成（offscreen 下用 exit 强制收尾；真实程序不受影响）
        QTimer.singleShot(2400, splash.finish)
        QTimer.singleShot(8200, app.exit)
        app.exec()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
