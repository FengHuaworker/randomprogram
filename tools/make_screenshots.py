# -*- coding: utf-8 -*-
"""
生成 README 用的界面截图（全部使用虚构名单，不涉及真实学生数据）。

用法：python tools/make_screenshots.py
输出：docs/img/*.png
"""

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
from PySide6.QtCore import QTimer  # noqa: E402

from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402

OUT = ROOT / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)

# 虚构名单（示例数据）
NAMES = ["王小明", "李小华", "张小强", "陈雨桐", "刘一诺", "赵子豪",
         "孙悦", "周天翔", "吴思彤", "郑浩然", "冯晨曦", "褚俊杰"]
DRAWN = [(5, "陈雨桐"), (8, "周天翔"), (11, "郑浩然"), (2, "李小华")]


def load_font():
    """offscreen 平台需要手动注册字体，优先宋体。"""
    for p in (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            QFontDatabase.addApplicationFont(p)
            break


def main():
    app = QApplication(sys.argv)
    load_font()
    theme.apply_theme(app)

    tmp = Path(tempfile.mkdtemp(prefix="shots_"))
    try:
        mgr = ClassManager(tmp)
        mgr.ensure_dirs()
        mgr.ensure_template()
        name = mgr.create_class("三年级1班")
        st = mgr.get_class(name)
        st.roster_write(NAMES)

        cfg = st.load_config()
        cfg["mode"] = MODE_ADVANCED
        cfg["total_count"] = len(NAMES)
        cfg["batch_count"] = 3
        st.save_config(cfg)
        st.set_long_exempt([4, 6])
        st.set_short_exempt([9])

        # 造几条已抽记录，让记录页/统计页有内容
        for num, who in DRAWN:
            st.add_history(num, who, MODE_ADVANCED)
            st.record_cooling(num)

        win = MainWindow(mgr)
        win.resize(1280, 800)
        win.show()
        app.processEvents()
        win._reload_class(name)
        app.processEvents()

        def save(tag):
            win.grab().save(str(OUT / f"{tag}.png"))
            print("saved:", tag)

        def mask_path():
            """把临时数据目录换成示意路径，避免截图里出现本机 Temp 路径。"""
            from app.ui_widgets import WrapLabel
            for v in win.config_page.findChildren(WrapLabel):
                s = v.text()
                if "Temp" in s or "shots_" in s:
                    v.setText(r"D:\随机抽号\classes\三年级1班")
                    v.fit()

        # 1) 抽号页：先真的抽一次，截图里才有定格结果
        def draw_page():
            win._on_nav_changed(0)
            QTimer.singleShot(400, win.draw_page.start)
            QTimer.singleShot(1500, win.draw_page.stop)
            QTimer.singleShot(2400, lambda: save("main_draw"))

        QTimer.singleShot(900, draw_page)

        # 2) 记录页
        QTimer.singleShot(3600, lambda: (win._on_nav_changed(1),
                                         QTimer.singleShot(500, lambda: save("history"))))

        # 3) 统计页
        QTimer.singleShot(4600, lambda: (win._on_nav_changed(2),
                                         QTimer.singleShot(800, lambda: save("stats"))))

        # 4) 配置页
        QTimer.singleShot(5800, lambda: (win._on_nav_changed(3),
                                         QTimer.singleShot(600, mask_path),
                                         QTimer.singleShot(1000, lambda: save("config"))))

        # 5) 屏蔽页
        QTimer.singleShot(7100, lambda: (win._on_nav_changed(4),
                                         QTimer.singleShot(500, lambda: save("shield"))))

        QTimer.singleShot(8200, app.exit)
        app.exec()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
