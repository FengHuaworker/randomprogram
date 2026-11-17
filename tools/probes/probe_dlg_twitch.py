# -*- coding: utf-8 -*-
"""逐帧记录弹窗显示过程中「什么变了」，定位抽搐来源。

关注三项：
  1. dialog 窗口几何（原生窗口被 setGeometry 移动/缩放）
  2. card 几何（布局重排导致卡片位置/尺寸跳变）
  3. scroll 高度 + 卡片 effect 参数（动画起点的位图尺寸变化）

用法：python tools/probes/probe_dlg_twitch.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QTimer

from app import theme
from app.ui_widgets import MaterialAlert, MaterialDialog


def sample(tag, dlg, log):
    card = dlg.card
    eff = card.graphicsEffect()
    s = getattr(eff, "s", None)
    a = getattr(eff, "a", None)
    log.append((
        dlg.geometry().getRect(),
        card.geometry().getRect(),
        dlg.scroll.height(),
        None if s is None else round(float(s), 3),
        None if a is None else round(float(a), 3),
        dlg.isVisible(),
    ))


def run(name, factory):
    app = QApplication.instance() or QApplication(sys.argv)
    host = QWidget()
    host.resize(1180, 760)
    host.setStyleSheet("background:#fff;")
    host.show()

    dlg = factory(host)
    log = []
    t = QTimer()
    t.setInterval(8)

    def tick():
        sample(name, dlg, log)

    t.timeout.connect(tick)
    t.start()
    dlg.show()
    QTimer.singleShot(1000, lambda: (t.stop(), report(name, log), dlg.close()))
    QTimer.singleShot(1150, lambda: None)
    app.processEvents()


def report(name, log):
    print(f"\n===== {name} =====")
    prev = None
    for i, row in enumerate(log):
        if row != prev:
            print(f"  t={i*8:4d}ms  win={row[0]}  card={row[1]}  scroll_h={row[2]}"
                  f"  s={row[3]} a={row[4]} vis={row[5]}")
            prev = row
    print(f"  采样 {len(log)} 帧，变化 {sum(1 for i in range(1, len(log)) if log[i] != log[i-1])} 次")


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\simsun.ttc")
    theme.apply_theme(app)

    host = QWidget()
    host.resize(1180, 760)
    host.setStyleSheet("background:#ffffff;")
    host.show()

    jobs = [
        ("MaterialAlert", lambda h: MaterialAlert(h, "提示", "这是一条普通提示，用来观察弹窗入场时是否抽搐。")),
        ("MaterialAlertLong", lambda h: MaterialAlert(
            h, "设置", "第一段说明文字，比较长，用来测试换行后的高度计算是否稳定。\n"
                     "第二段说明文字，继续加长，确保正文会有多行折行的情况出现。\n"
                     "第三段说明文字，再补一点内容。")),
    ]

    state = {"i": 0}

    def step():
        if state["i"] >= len(jobs):
            app.exit()
            return
        name, factory = jobs[state["i"]]
        state["i"] += 1
        dlg = factory(host)
        log = []
        t = QTimer()
        t.setInterval(8)
        t.timeout.connect(lambda: sample(name, dlg, log))
        t.start()
        dlg.show()

        def done():
            t.stop()
            report(name, log)
            dlg.close()
            QTimer.singleShot(120, step)

        QTimer.singleShot(1000, done)

    QTimer.singleShot(60, step)
    app.exec()


if __name__ == "__main__":
    main()
