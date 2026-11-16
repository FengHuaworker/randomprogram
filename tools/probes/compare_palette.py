# -*- coding: utf-8 -*-
"""对照：页面底色更深一点，卡片/投影的层次与动效可见度是否明显提升。
用法：python tools/compare_palette.py [deep]
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from app import theme

if "deep" in sys.argv:
    theme.COLORS["surface"] = "#EFF1F6"
    theme.COLORS["surface_container_low"] = "#F7F8FB"
    theme.COLORS["surface_container"] = "#EBEDF3"
    theme.COLORS["surface_container_high"] = "#E5E8EF"

theme.register_fonts(str(Path(__file__).resolve().parents[1]))
theme.apply_theme(app)

from app.app_data import ClassManager
from tools._probe_env import temp_classes
from app.ui_main import MainWindow

mgr = ClassManager(temp_classes())
mgr.ensure_dirs()
win = MainWindow(mgr)
win.setWindowTitle("PALETTE")
win.showMaximized()
for _ in range(200):
    app.processEvents()
    if win.store is not None:
        break
t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.2:
    app.processEvents()
    time.sleep(0.002)

out = Path("ui_preview")
out.mkdir(exist_ok=True)
# 造一个结果态，画面更接近真实使用
dp = win.draw_page
try:
    dp.num_label.set_now("42")
    dp.name_label.setText("张子墨")
    dp.caption.setText("本轮第 7 位")
    dp._apply_num_size(2)
    win.draw_page.result.set_watermark(False)
except Exception as e:
    print("decorate fail", e)
app.processEvents()
tag = "deep" if "deep" in sys.argv else "base"
win.grab().save(str(out / f"palette_{tag}.png"))
print("saved", out / f"palette_{tag}.png")
