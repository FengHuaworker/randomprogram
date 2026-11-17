# -*- coding: utf-8 -*-
"""逐帧抓**屏幕**（用户实际看到的合成画面），量卡片包围盒，找出抽搐的那一帧。

为什么不用 widget.grab()：那拿到的是控件自己渲染的结果，绕过合成器；
而抽搐发生在合成/绘制层面（透明窗口、分层表面）。屏幕抓取才是用户视角。

宿主窗口故意用深色底：遮罩是半透明黑，卡片是最浅白，两者对比明显，
从第一帧就能量出卡片位置。

用法：python tools/probes/probe_screen_frames.py [标签]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtCore import QTimer, QRect

from app import theme
from app.ui_widgets import MaterialAlert

OUT = ROOT / "tools" / "_shots" / "_seq"


def bbox(img):
    w, h = img.width(), img.height()
    buf = bytes(img.constBits())
    arr = np.frombuffer(buf, dtype=np.uint8)[: w * h * 4].reshape(h, w, 4)
    mask = (arr[:, :, 0] > 238) & (arr[:, :, 1] > 238) & (arr[:, :, 2] > 238)
    ys, xs = np.nonzero(mask)
    if xs.size < 400:          # 太小当成噪点
        return None
    return (int(xs.min()), int(ys.min()),
            int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "seq"
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\simsun.ttc")
    theme.apply_theme(app)

    host = QWidget()
    host.setWindowTitle("probe-host")
    host.resize(1000, 700)
    host.setStyleSheet("background:#2b2f36;")
    host.show()
    host.raise_()
    host.activateWindow()
    app.processEvents()

    screen = QGuiApplication.primaryScreen()
    geo = host.frameGeometry()

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    dlg = MaterialAlert(host, "提示", "这是一条普通提示，用来观察弹窗入场时是否抽搐。")

    frames = []
    t = QTimer()
    t.setInterval(0)          # 尽可能连续采样

    def tick():
        img = screen.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height()).toImage()
        bb = bbox(img)
        i = len(frames)
        frames.append(bb)
        if i < 60:
            img.save(str(OUT / f"{label}_{i:02d}.png"))

    t.timeout.connect(tick)
    t.start()
    dlg.show()
    dlg.raise_()

    def done():
        t.stop()
        print(f"\n[{label}] 共 {len(frames)} 帧（屏幕抓取）")
        prev = None
        for i, bb in enumerate(frames):
            if bb is None:
                print(f"{i:02d} | 无卡片")
                prev = None
                continue
            d = "" if prev is None else (
                f"   dx={bb[0]-prev[0]:+4d} dy={bb[1]-prev[1]:+4d}"
                f" dw={bb[2]-prev[2]:+4d} dh={bb[3]-prev[3]:+4d}")
            print(f"{i:02d} | {bb}{d}")
            prev = bb
        dlg.close()
        QTimer.singleShot(120, app.exit)

    QTimer.singleShot(1100, done)
    app.exec()


if __name__ == "__main__":
    main()
