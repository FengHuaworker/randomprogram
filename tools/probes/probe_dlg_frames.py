# -*- coding: utf-8 -*-
"""逐帧抓弹窗画面，量卡片的实际像素包围盒 + 透明度，找出「抽搐」那一帧。

判定：卡片底色是最浅的白（surface_container_lowest），遮罩是半透明黑。
每帧取 RGB 全 > 240 的像素包围盒 = 卡片可见区域。
正常入场是单调放大；若某一帧尺寸/位置突变再回弹，就是抽搐源。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtCore import QTimer

from app import theme
from app.ui_widgets import MaterialAlert

OUT = ROOT / "tools" / "_shots" / "_dlg_frames"
OUT.mkdir(parents=True, exist_ok=True)


def card_bbox(img: QImage):
    """用 numpy 一次算完，纯 Python 逐像素太慢（900k 像素/帧）。"""
    import numpy as np
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = img.constBits()
    arr = np.frombuffer(bytes(buf), dtype=np.uint8)[: w * h * 4].reshape(h, w, 4)
    mask = (arr[:, :, 3] > 200) & (arr[:, :, 0] > 240) & \
           (arr[:, :, 1] > 240) & (arr[:, :, 2] > 240)
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\simsun.ttc")
    theme.apply_theme(app)

    host = QWidget()
    host.resize(1180, 760)
    host.setStyleSheet("background:#ffffff;")
    host.show()

    dlg = MaterialAlert(host, "提示", "这是一条普通提示，用来观察弹窗入场时是否抽搐。")

    frames = []
    t = QTimer()
    t.setInterval(8)

    def tick():
        idx = len(frames)
        img = dlg.grab().toImage()
        bb = card_bbox(img)
        frames.append(bb)
        if idx < 30:
            img.save(str(OUT / f"f{idx:02d}.png"))

    t.timeout.connect(tick)
    t.start()
    dlg.show()

    def done():
        t.stop()
        print("\n帧 | 卡片包围盒 (x, y, w, h) | 相对上一帧的变化")
        prev = None
        for i, bb in enumerate(frames):
            if bb is None:
                print(f"{i:02d} | None")
                prev = None
                continue
            d = "" if prev is None else (
                f"  dx={bb[0]-prev[0]:+d} dy={bb[1]-prev[1]:+d}"
                f" dw={bb[2]-prev[2]:+d} dh={bb[3]-prev[3]:+d}")
            print(f"{i:02d} | {bb}{d}")
            prev = bb
        dlg.close()
        QTimer.singleShot(80, app.exit)

    QTimer.singleShot(900, done)
    app.exec()


if __name__ == "__main__":
    main()
