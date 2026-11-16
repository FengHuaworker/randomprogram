# -*- coding: utf-8 -*-
"""v2「朱墨」界面预览：可指定窗口尺寸与输出前缀，用于多尺寸/多缩放验收。"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def main():
    size = os.environ.get("PREVIEW_SIZE", "1366x820")
    prefix = os.environ.get("PREVIEW_PREFIX", "v2")
    w, h = (int(x) for x in size.lower().split("x"))

    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/simsun.ttc")
    theme.apply_theme(app)

    tmp = Path(tempfile.mkdtemp(prefix="preview_v2_"))
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
        win.resize(w, h)
        win.show()
        QTest.qWait(200)
        win._reload_class(n)
        QTest.qWait(900)
        win.grab().save(str(OUT / f"{prefix}_main.png"))

        # 抽号中
        win.draw_page.start()
        QTest.qWait(300)
        win.grab().save(str(OUT / f"{prefix}_rolling.png"))
        win.draw_page.stop()
        QTest.qWait(900)
        win.grab().save(str(OUT / f"{prefix}_freeze.png"))

        # 批量
        picks = [{"num": i, "name": NAMES[i - 1]} for i in (2, 5, 8, 11, 14, 17)]
        ov = BatchRevealOverlay(win, picks, [s["num"] for s in win.draw_page._pool])
        ov.show(); ov.raise_(); ov.start()
        QTest.qWait(350)
        win.grab().save(str(OUT / f"{prefix}_batch_roll.png"))
        QTest.qWait(2400)
        win.grab().save(str(OUT / f"{prefix}_batch_done.png"))
        ov.close_overlay(); QTest.qWait(150)

        # 其他页
        for idx, page in ((1, win.history_page), (2, win.stats_page),
                          (3, win.config_page), (4, win.shield_page)):
            win.nav.setCurrentIndex(idx)
            win.stack.setCurrentWidget(page)
            page.refresh()
            QTest.qWait(500)
            win.grab().save(str(OUT / f"{prefix}_page{idx}.png"))

        # 弹窗
        pwd = AdminPasswordDialog(win); pwd.show(); QTest.qWait(350)
        pwd.grab().save(str(OUT / f"{prefix}_admin.png")); pwd.close()
        clean = HistoryCleanupDialog(win, st); clean.show(); QTest.qWait(350)
        clean.grab().save(str(OUT / f"{prefix}_clean.png")); clean.close()

        win.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("done", prefix, size)


if __name__ == "__main__":
    main()
