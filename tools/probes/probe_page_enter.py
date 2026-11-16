# -*- coding: utf-8 -*-
"""诊断「进入抽号页」动画的两个观感缺陷：
1) 首帧是否在动画启动前就以全亮渲染（闪一下再淡入）；
2) hero 的原生投影 effect 是否被 MotionEffect 顶掉（卡片变平板）。
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from app.ui_main import MainWindow
from app.app_data import ClassManager
from tools._probe_env import temp_classes

mgr = ClassManager(temp_classes())
mgr.ensure_dirs()
win = MainWindow(mgr)
win.setWindowTitle("ENTER PROBE")
win.showMaximized()
for _ in range(200):
    app.processEvents()
    if win.store is not None:
        break
time.sleep(0.4)
app.processEvents()


def eff_name(w):
    e = w.graphicsEffect()
    return type(e).__name__ if e is not None else "None"


def drain(ms):
    t0 = time.perf_counter()
    while (time.perf_counter() - t0) * 1000 < ms:
        app.processEvents()
        time.sleep(0.002)


hero = win.draw_page.hero
batch = win.draw_page.batch_card
page = win.draw_page

print("初始 hero effect      :", eff_name(hero))
print("初始 batch effect     :", eff_name(batch))
print("初始 page effect      :", eff_name(page))


def alpha_of(w):
    e = w.graphicsEffect()
    return getattr(e, "a", None) if e is not None else None


# 切到历史页，再切回抽号页，观察首帧状态
win.nav.setCurrentIndex(1, emit=True)
drain(700)
print("切到历史页后 hero      :", eff_name(hero), " 历史页 effect:",
      eff_name(win.history_page))

win.nav.setCurrentIndex(0, emit=True)
print("切回抽号页 t=0        : page=%s a=%s   <- a 应已是 0（否则首帧全亮会闪）"
      % (eff_name(page), alpha_of(page)))
drain(60)
print("切回抽号页 t=60ms     : page=%s a=%.2f" % (eff_name(page), alpha_of(page) or -1))
drain(900)
print("切回抽号页 t=960ms    : page=%s  hero=%s  <- hero 应恢复原生投影"
      % (eff_name(page), eff_name(hero)))
print("done")
