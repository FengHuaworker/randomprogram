# -*- coding: utf-8 -*-
"""特效对齐回归测试：带出框留白（bleed）的 MotionEffect 在「位移 0 / 缩放 1」
时，渲染结果必须和没有特效时**逐像素重合**。

背景：boundingRectFor 扩大后，sourcePixmap 返回的位图比控件大一圈并带负
偏移；早先按 (0,0) 绘制，导致动效期间整个内容偏移 bleed 像素、结束再弹回，
观感就是「窗口弹出时水平跳一下」。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QPainter, QImage
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)
from app.motion import MotionEffect


class Mark(QWidget):
    """白底 + 左上角红块 + 中间一条竖线，位置敏感。"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 300)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        p.fillRect(20, 20, 40, 40, QColor("#FF0000"))
        p.fillRect(200, 0, 2, 300, QColor("#0000FF"))
        p.end()


def render(w):
    img = QImage(w.width(), w.height(), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    w.render(p, QPoint(0, 0))
    p.end()
    return img


def find(img, pred):
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            if pred(c):
                return (x, y)
    return None


w = Mark()
w.show()
app.processEvents()
base_img = render(w)
base_red = find(base_img, lambda c: c.red() > 200 and c.green() < 80)

eff = MotionEffect(w)
eff._bleed = 40.0
# 位置参数全为「无变换」，只留透明度差异逼出变换分支
eff.set_values(s=1.0, dx=0.0, dy=0.0, a=0.999)
w.setGraphicsEffect(eff)
w.update()
for _ in range(5):
    app.processEvents()
eff_img = render(w)
eff_red = find(eff_img, lambda c: c.red() > 200 and c.green() < 80)

dx = dy = 999
if base_red and eff_red:
    dx, dy = eff_red[0] - base_red[0], eff_red[1] - base_red[1]
print(f"无特效红块起点={base_red}  有特效(bleed=40)起点={eff_red}  偏移=({dx},{dy})")
ok = (dx == 0 and dy == 0)
print("PASS" if ok else "FAIL", "特效绘制原点对齐" if ok else "特效导致内容偏移")
sys.exit(0 if ok else 1)
