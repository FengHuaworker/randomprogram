# -*- coding: utf-8 -*-
"""悬浮球/迷你卡/全屏层的离屏截图，用于人工检查排版与重叠。

用法：QT_QPA_PLATFORM=offscreen python tools/preview_float.py
输出：video/float_check/*.png
"""

import os
import sys
import tempfile
import shutil
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "video" / "float_check"
OUT.mkdir(parents=True, exist_ok=True)

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QFontDatabase, QPixmap, QColor  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402

from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402
from app.ui_float import FloatDock, DimOverlay  # noqa: E402

NAMES = ["王小明", "李小华", "张小强", "陈雨桐", "刘一诺", "赵子豪",
         "孙悦", "周天翔", "吴思彤", "郑浩然", "冯晨曦", "褚俊杰"]
DRAWN = [(5, "陈雨桐"), (8, "周天翔"), (11, "郑浩然")]


def load_font():
    for p in (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            QFontDatabase.addApplicationFont(p)
            return


def render(widget, path, scale=1, bg=None):
    """把控件渲染成 PNG；bg 为 None 时保留透明。"""
    widget.setWindowOpacity(1.0)
    w, h = widget.width(), widget.height()
    pm = QPixmap(int(w * scale), int(h * scale))
    pm.fill(QColor(0, 0, 0, 0) if bg is None else QColor(bg))
    pm.setDevicePixelRatio(scale)
    widget.render(pm, QPoint(0, 0))
    pm.save(str(path))
    print("saved", path.name, widget.size().width(), "x", widget.size().height())


def main():
    app = QApplication(sys.argv)
    load_font()
    theme.apply_theme(app)

    tmp = Path(tempfile.mkdtemp(prefix="float_", dir=str(ROOT / ".tmp")))
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
        st.save_config(cfg)
        for num, who in DRAWN:
            st.record_draws([{"num": num, "name": who}], MODE_ADVANCED, True)

        win = MainWindow(mgr)
        win.resize(1280, 800)
        win.show()
        app.processEvents()
        win._reload_class(name)
        app.processEvents()

        dock = FloatDock(win, enable_tray=False)
        dock.known = True
        dock.ready = True
        dock.ball.move(0, 300)
        dock.ball._rest_pos = dock.ball.pos()
        dock.ball.show_in(animate=False)
        app.processEvents()

        # 球：常态 / hover / 抽号中
        dock.ball._breath = 0.34
        dock.ball._hover = 0.0
        dock.ball.set_running(False)
        dock.ball.update()
        render(dock.ball, OUT / "ball_idle.png", scale=3)

        dock.ball._hover = 1.0
        dock.ball.update()
        render(dock.ball, OUT / "ball_hover.png", scale=3)

        dock.ball._hover = 0.0
        dock.ball.set_running(True)
        dock.ball._spin = 0.3
        dock.ball.update()
        render(dock.ball, OUT / "ball_running.png", scale=3)
        dock.ball.set_running(False)

        # 卡片：空态
        dock.card.open_for(dock.ball)
        app.processEvents()
        dock.card._reveal_anim.stop()
        dock.card._reveal = 0.46
        dock.card.update()
        render(dock.card, OUT / "card_reveal.png", scale=2)
        dock.card._reveal = 1.0
        dock.card._count = 3
        dock.card._state = "empty"
        dock.card._num = ""
        dock.card._name = ""
        dock.card.update()
        render(dock.card, OUT / "card_empty.png", scale=2)

        # 卡片：抽号中
        dock.card._state = "rolling"
        dock.card._running = True
        dock.card._num = "07"
        dock.card._prev = "12"
        dock.card.update()
        render(dock.card, OUT / "card_rolling.png", scale=2)
        dock.card._running = False

        # 卡片：结果
        dock.card._state = "result"
        dock.card._num = "03"
        dock.card._prev = "11"
        dock.card._roll_t = 1.0
        dock.card._name = "张小强"
        dock.card._name_t = 1.0
        dock.card._halo = 0.55
        dock.card._count = 4
        dock.card.update()
        render(dock.card, OUT / "card_result.png", scale=2)

        # 卡片：重置二次确认
        dock.card._halo = 0.0
        dock.card._reset_until = time.perf_counter() + 20
        dock.card.update()
        render(dock.card, OUT / "card_reset.png", scale=2)

        # 球在右缘时，卡片应从右向左展开且不出屏
        dock.card.close(instant=True)
        scr = dock.screen_at(dock.ball.geometry().center())
        avail = scr.availableGeometry()
        dock.ball.move(avail.right() - dock.ball.width() + 1, 300)
        dock.ball._rest_pos = dock.ball.pos()
        dock.card.open_for(dock.ball)
        app.processEvents()
        dock.card._reveal_anim.stop()
        dock.card._reveal = 1.0
        dock.card._state = "result"
        dock.card._num = "08"
        dock.card._prev = "08"
        dock.card._roll_t = 1.0
        dock.card._name = "周天翔"
        dock.card._name_t = 1.0
        dock.card._count = 5
        dock.card.update()
        render(dock.card, OUT / "card_right.png", scale=2)
        print("card geometry", dock.card.geometry(), "ball", dock.ball.geometry())
        dock.card.close(instant=True)

        # 全屏层：滚动中 / 落定
        for tag, state in (
            ("overlay_rolling", dict(dim=0.96, alpha=1.0, panel_in=1.0,
                                     num="07", prev="12", roll_t=1.0,
                                     rolling=True, name="张小强", name_t=0.0,
                                     halo=0.0, footer="已记录 · 第 4 位",
                                     footer_t=0.0)),
            ("overlay_result", dict(dim=1.0, alpha=1.0, panel_in=1.0,
                                    num="03", prev="11", roll_t=1.0,
                                    rolling=False, name="张小强", name_t=1.0,
                                    halo=0.62, footer="已记录 · 第 4 位",
                                    footer_t=1.0)),
        ):
            ov = DimOverlay(app.primaryScreen())
            ov.setFixedSize(1600, 900)
            ov.is_content = True
            ov.set_state(**state)
            ov.show()
            app.processEvents()
            render(ov, OUT / f"{tag}.png", bg=None)
            ov.hide()
            ov.deleteLater()
            app.processEvents()

            # 合成到真实主界面截图上，检查压暗后的可读性
            try:
                from PIL import Image
                desk = Image.open(ROOT / "docs" / "img" / "main_draw.png")
                desk = desk.convert("RGB").resize((1600, 900), Image.LANCZOS)
                layer = Image.open(OUT / f"{tag}.png").convert("RGBA")
                desk.paste(layer, (0, 0), layer)
                desk.save(OUT / f"{tag}_on_desktop.png")
                print("saved", f"{tag}_on_desktop.png")
            except Exception as exc:
                print("composite skipped:", exc)

        # 主界面顺带看一眼（悬浮球不应影响它）
        win.showNormal()
        app.processEvents()
        render(win, OUT / "main_window.png", bg="#FFFFFF")

        dock.ball.hide_out(animate=False)
        dock.card.close(instant=True)
        print("done ->", OUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
