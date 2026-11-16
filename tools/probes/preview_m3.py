# -*- coding: utf-8 -*-
"""M3 版界面预览：offscreen 截图，检查视觉、布局与批量揭晓动画。"""

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
from PySide6.QtTest import QTest  # noqa: E402

from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402
from app.ui_dialogs import AdminPasswordDialog, HistoryCleanupDialog  # noqa: E402
from app.ui_widgets import BatchRevealOverlay  # noqa: E402

OUT = ROOT / "ui_preview"
OUT.mkdir(exist_ok=True)

NAMES = ["王小明", "李小华", "张小强", "陈雨桐", "刘一诺", "赵子豪",
         "孙悦", "周天翔", "吴思彤", "郑浩然", "冯晨曦", "褚俊杰",
         "卫子涵", "蒋雨欣", "沈嘉懿", "韩沐辰", "杨若曦", "朱一鸣"]


def dev_fonts():
    # offscreen 平台没有系统字体：直接注册 Windows 宋体，保证截图与真实机一致
    for p in (Path("C:/Windows/Fonts/simsun.ttc"),
              ROOT / "tools" / "qtfonts" / "msyh.ttc"):
        if p.exists():
            QFontDatabase.addApplicationFont(str(p))


def save(w, name):
    w.grab().save(str(OUT / f"{name}.png"))
    print("saved", name)


def main():
    app = QApplication(sys.argv)
    dev_fonts()
    theme.apply_theme(app)
    tmp = Path(tempfile.mkdtemp(prefix="preview_m3_"))
    try:
        mgr = ClassManager(tmp)
        mgr.ensure_dirs()
        n = mgr.create_class("三年级1班")
        st = mgr.get_class(n)
        st.roster_write(NAMES)
        cfg = st.load_config()
        cfg["mode"] = MODE_ADVANCED
        cfg["total_count"] = len(NAMES)
        st.save_config(cfg)
        st.set_long_exempt([15])
        st.set_short_exempt([7])
        st.record_draws([{"num": 3, "name": "张小强"}, {"num": 9, "name": "吴思彤"},
                         {"num": 12, "name": "褚俊杰"}], MODE_ADVANCED, anti_dup=True)

        win = MainWindow(mgr)
        win.resize(1366, 820)
        win.show()
        QTest.qWait(300)
        win._reload_class(n)
        QTest.qWait(700)
        save(win, "m3_draw")

        win.nav.setCurrentIndex(1)
        win.stack.setCurrentWidget(win.history_page)
        win.history_page.refresh()
        QTest.qWait(500)
        save(win, "m3_history")

        win.nav.setCurrentIndex(2)
        win.stack.setCurrentWidget(win.stats_page)
        win.stats_page.refresh()
        QTest.qWait(700)
        save(win, "m3_stats")

        win.nav.setCurrentIndex(3)
        win.stack.setCurrentWidget(win.config_page)
        win.config_page.refresh()
        QTest.qWait(700)
        save(win, "m3_config")

        win.nav.setCurrentIndex(4)
        win.stack.setCurrentWidget(win.shield_page)
        win.shield_page.refresh()
        QTest.qWait(500)
        save(win, "m3_shield")

        win.nav.setCurrentIndex(0)
        win.stack.setCurrentWidget(win.draw_page)
        QTest.qWait(300)

        # 单抽：滚动 / 定格
        win.draw_page.start()
        QTest.qWait(280)
        save(win, "m3_rolling")
        win.draw_page.stop()
        QTest.qWait(220)
        save(win, "m3_freeze")

        # 池空自动重置横幅
        win.draw_page._show_reset_banner(13)
        QTest.qWait(400)
        save(win, "m3_reset_banner")

        # 批量揭晓：滚动阶段
        picks = [{"num": i, "name": NAMES[i - 1]} for i in (2, 5, 8, 11, 14, 17)]
        ov = BatchRevealOverlay(win, picks, [s["num"] for s in win.draw_page._pool])
        ov.show()
        ov.raise_()
        ov.start()
        QTest.qWait(420)
        save(win, "m3_batch_rolling")
        QTest.qWait(2600)
        save(win, "m3_batch_done")
        ov.close_overlay()
        QTest.qWait(200)

        # 管理员验证 / 记录清理
        pwd = AdminPasswordDialog(win)
        pwd.show()
        QTest.qWait(400)
        save(pwd, "m3_admin")
        pwd.close()

        clean = HistoryCleanupDialog(win, st)
        clean.show()
        QTest.qWait(400)
        save(clean, "m3_clean")
        clean.close()

        win.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
