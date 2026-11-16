# -*- coding: utf-8 -*-
"""验证 ResultStage.fire_halo：光环确实画在舞台内（grab 可捕获 paintEvent 内容），
且不会无限残留。用法：python tools/halo_check.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

from app.ui_pages import ResultStage

P = ROOT / "ui_preview"
stage = ResultStage()
stage.setFixedSize(600, 340)
stage.setStyleSheet("background:#FFFFFF;")
stage.show()
app.processEvents()

base = stage.grab()
base.save(str(P / "halo_off.png"))

stage.fire_halo(theme.COLORS["primary"], max_r=190, dur=900)

import time
t0 = time.perf_counter()
shots = 0
while time.perf_counter() - t0 < 0.5:
    app.processEvents()
    time.sleep(0.002)
mid = stage.grab()
mid.save(str(P / "halo_mid.png"))
shots += 1


def diff_pixels(a, b):
    """统计两张图不同的像素数（光环应产生一批差异像素）。"""
    ia, ib = a.toImage(), b.toImage()
    if ia.size() != ib.size():
        return -1
    n = 0
    for y in range(0, ia.height(), 2):
        for x in range(0, ia.width(), 2):
            if ia.pixelColor(x, y) != ib.pixelColor(x, y):
                n += 1
    return n


d = diff_pixels(base, mid)
print(f"halo 期间差异像素(抽样) = {d}")

# 等光环结束，确认自动关闭（画面回到无光环）
t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.0:
    app.processEvents()
    time.sleep(0.005)
end = stage.grab()
end.save(str(P / "halo_end.png"))
d2 = diff_pixels(base, end)
print(f"halo 结束后差异像素(抽样) = {d2}")

ok = d > 50 and d2 == 0
print("PASS" if ok else "FAIL", "光环绘制且自动关闭" if ok else f"d={d} d2={d2}")
app.quit()
sys.exit(0 if ok else 1)
