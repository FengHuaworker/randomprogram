# -*- coding: utf-8 -*-
"""视觉检查：hero 烘焙投影是否自然、正文位置是否被挤动。"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from app import theme
theme.register_fonts(str(Path(__file__).resolve().parents[1]))
theme.apply_theme(app)

from app.app_data import ClassManager
from tools._probe_env import temp_classes
from app.ui_main import MainWindow

mgr = ClassManager(temp_classes())
mgr.ensure_dirs()
win = MainWindow(mgr)
win.setWindowTitle("SHADOW CHECK")
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
hero = win.draw_page.hero
hero.grab().save(str(out / "hero_baked_shadow.png"))
win.draw_page.grab().save(str(out / "page_enter_final.png"))
print("hero size", hero.size().width(), hero.size().height())
print("saved", out / "hero_baked_shadow.png")
print("saved", out / "page_enter_final.png")
