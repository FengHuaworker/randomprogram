# -*- coding: utf-8 -*-
"""量「结果出现」瞬间是否因滚动条出现/消失导致内容横向平移。

抽号前 content 里没有姓名/印章；抽号后多出两行 -> 内容变高 -> 可能出现
垂直滚动条。滚动条占宽 => 视口变窄 => 卡片与大数字整体左移，这就是用户
看到的「水平跳一下」。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from tools._probe_env import temp_classes
from app import theme
from app.app_data import ClassManager
from app.ui_main import MainWindow


def run(w, h):
    app = QApplication.instance() or QApplication(sys.argv)
    theme.register_fonts(".")
    theme.apply_theme(app)
    base = temp_classes(f"rp_sb_{w}x{h}_")
    win = MainWindow(ClassManager(str(base)))
    win.startup()
    win.resize(w, h)
    win.show()
    app.processEvents()
    time.sleep(0.25)
    app.processEvents()

    page = win.draw_page
    sb = page.scroll.verticalScrollBar()

    def snap(tag):
        vp = page.scroll.viewport()
        # content 相对 viewport 的 x（滚动条出现会让它从 0 变成 0，但宽度变小）
        print(f"  {tag:8s} sbVisible={sb.isVisible():d} "
              f"sbMax={sb.maximum():4d} vpW={vp.width():4d} "
              f"contentW={page.content.width():4d} "
              f"heroX={page.hero.mapTo(page.content, page.hero.rect().topLeft()).x():4d} "
              f"heroW={page.hero.width():4d} "
              f"numCenter={page.num_label.mapTo(page.content, page.num_label.rect().center()).x():4d}")
        return vp.width(), page.hero.mapTo(page.content, page.hero.rect().topLeft()).x()

    print(f"[{w}x{h}]")
    vp0, hx0 = snap("before")
    page.toggle()
    t = time.time()
    while time.time() - t < 0.35:
        app.processEvents()
        time.sleep(0.01)
    page.toggle()
    t = time.time()
    while time.time() - t < 1.4:
        app.processEvents()
        time.sleep(0.01)
    vp1, hx1 = snap("after")
    print(f"  => ΔviewportW={vp1 - vp0}  ΔheroX={hx1 - hx0}")
    win.close()


for size in [(1536, 912), (1400, 860), (1280, 800), (1100, 720), (1000, 660), (920, 620)]:
    run(*size)
