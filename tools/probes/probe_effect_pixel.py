# -*- coding: utf-8 -*-
"""像素级验证 MotionEffect 在 DPR=1 / 1.25 下的落点与残影。

三个问题一次测清：
  A. 效果开启 + 无变换时，内容是否仍在控件原位（偏移=0）？
  B. 效果放大 s>1（出框）时，内容中心是否与控件中心重合？
  C. 动画结束后把效果禁用，父控件上是否残留「鬼影」（出框区域的旧像素）？

判定全部用像素包围盒，不依赖肉眼。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget, QFrame

from app import motion


def render(widget) -> QImage:
    img = QImage(widget.size() * widget.devicePixelRatioF(),
                 QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(widget.devicePixelRatioF())
    img.fill(Qt.transparent)
    p = QPainter(img)
    widget.render(p, QPoint(0, 0))
    p.end()
    return img


def bbox_of(img: QImage, rgb=(220, 40, 40)):
    """找到接近指定颜色的像素包围盒（设备像素坐标 / DPR 还原成逻辑坐标）。"""
    dpr = img.devicePixelRatio()
    w, h = img.width(), img.height()
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            c = img.pixelColor(x, y)
            if c.alpha() > 40 and abs(c.red() - rgb[0]) < 40 \
                    and abs(c.green() - rgb[1]) < 40 and abs(c.blue() - rgb[2]) < 40:
                if x < x0: x0 = x
                if y < y0: y0 = y
                if x > x1: x1 = x
                if y > y1: y1 = y
    if x1 < 0:
        return None
    return (x0 / dpr, y0 / dpr, (x1 + 1) / dpr, (y1 + 1) / dpr)


class Swatch(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(220, 40, 40))
        p.end()


def run(app):
    dpr = app.primaryScreen().devicePixelRatio()
    print(f"\n=== DPR = {dpr} ===")
    host = QWidget()
    host.setAttribute(Qt.WA_StyledBackground, False)
    host.resize(400, 300)
    host.setStyleSheet("background:#EEEEEE;")

    class Host(QWidget):
        def paintEvent(self, e):
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(238, 238, 238))
            p.end()

    host = Host()
    host.resize(400, 300)
    host.show()
    app.processEvents()

    child = Swatch(host)
    child.setGeometry(100, 80, 160, 90)
    child.show()
    app.processEvents()

    base = bbox_of(render(host))
    print(f"  静止（无效果）        色块包围盒 = {base}   期望 (100, 80, 260, 170)")

    # A. 效果开启 + 无变换（模拟动画结束状态）
    motion.prepare_entry(child, a=1.0)
    app.processEvents()
    eff = child.graphicsEffect()
    eff.set_values(s=1.0, dx=0.0, dy=0.0, a=1.0)
    host.repaint()
    app.processEvents()
    a = bbox_of(render(host))
    print(f"  A 无变换 + 效果启用   色块包围盒 = {a}   偏移 = "
          f"{None if not a else (round(a[0]-base[0], 2), round(a[1]-base[1], 2))}")

    # B. 放大 1.2（出框），中心应不变
    eff.set_values(s=1.2, dx=0.0, dy=0.0, a=1.0)
    host.repaint()
    app.processEvents()
    b = bbox_of(render(host))
    if b:
        cx0 = (base[0] + base[2]) / 2
        cx = (b[0] + b[2]) / 2
        print(f"  B 放大 1.2            色块包围盒 = {b}   中心 x {cx0} -> {cx} "
              f"(Δ={cx-cx0:+.2f})  宽 {base[2]-base[0]} -> {b[2]-b[0]}")
    else:
        print("  B 放大 1.2            未找到色块（被裁切）")

    # C. 动画结束：复位 + 禁用效果，看父控件是否留下残影
    eff.set_values(s=1.0, dx=0.0, dy=0.0, a=1.0)
    eff._bleed = 0.0
    eff.setEnabled(False)
    host.repaint()
    app.processEvents()
    c = bbox_of(render(host), rgb=(0, 0, 0))
    print(f"  C 效果禁用后黑像素包围盒 = {c}   （应为 None = 无残影）")

    # D. 纯平移 +6px：内容应整体右移 6
    eff.setEnabled(True)
    eff._bleed = 20.0
    eff.invalidate()
    eff.set_values(s=1.0, dx=6.0, dy=0.0, a=1.0)
    host.repaint()
    app.processEvents()
    d = bbox_of(render(host))
    print(f"  D 平移 +6px           色块包围盒 = {d}   期望左边 {base[0]+6}")

    host.close()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    run(app)
    # 再跑一遍 1.25 倍缩放
    os.environ["QT_SCALE_FACTOR"] = "1.25"
    print("\n（提示：QT_SCALE_FACTOR 需在 QApplication 之前设置，见下方子进程）")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scaled":
        os.environ["QT_SCALE_FACTOR"] = "1.25"
        app = QApplication(sys.argv)
        run(app)
    else:
        main()
