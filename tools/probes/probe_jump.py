# -*- coding: utf-8 -*-
"""定位「抽号完成后水平跳一下」：记录动画期间所有子控件的几何变化、
以及 MotionEffect 每帧实际绘制的落点（含父链映射），找出真实位移来源。

判定口径：控件在**窗口坐标系**里的左上角 x。只要某一帧相对上一帧变了，
就打印「谁、从多少到多少、什么时候」。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, QPoint
from PySide6.QtWidgets import QApplication, QWidget

from app import motion
from tools._probe_env import temp_classes

TRACE = {"on": False}
RECORDS = []          # (t_ms, kind, text)
ORIG_DRAW = motion.MotionEffect.draw


def _name(w):
    cls = type(w).__name__
    nm = w.objectName()
    return f"{cls}#{nm}" if nm else cls


def _win_pos(w, top):
    p = w.mapTo(top, QPoint(0, 0))
    return p.x(), p.y()


def _hook_draw(self, painter):
    if TRACE["on"]:
        w = self._widget()
        if w is not None:
            RECORDS.append((time.perf_counter(),
                            "draw",
                            (id(w), _name(w), round(self.s, 3), round(self.dx, 2),
                             round(self.dy, 2), round(self.a, 3),
                             self._bleed, self._src_off.x(), self._src_off.y(),
                             (self._src.width(), self._src.height()) if self._src else None,
                             (w.width(), w.height()))))
    return ORIG_DRAW(self, painter)


motion.MotionEffect.draw = _hook_draw


class GeoSpy(QObject):
    def __init__(self, top):
        super().__init__()
        self.top = top
        self.last = {}

    def eventFilter(self, obj, ev):
        if not TRACE["on"] or not isinstance(obj, QWidget):
            return False
        if ev.type() in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide):
            key = id(obj)
            geo = obj.geometry()
            prev = self.last.get(key)
            cur = (geo.x(), geo.y(), geo.width(), geo.height())
            if prev != cur:
                self.last[key] = cur
                RECORDS.append((time.perf_counter(), "geo",
                                (key, _name(obj), prev, cur)))
        return False


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from app.app_data import ClassManager
    from app.ui_main import MainWindow

    base = temp_classes("rp_jump_")
    win = MainWindow(ClassManager(str(base)))
    win.startup()
    win.resize(1280, 800)
    win.show()
    app.processEvents()

    spy = GeoSpy(win)
    for w in win.findChildren(QWidget):
        w.installEventFilter(spy)
    win.installEventFilter(spy)

    page = win.draw_page
    # 先把页面塞满真实内容（开启一次抽号流程）
    TRACE["on"] = True
    t0 = time.perf_counter()
    page.toggle()                       # 开始
    for _ in range(12):
        app.processEvents()
        time.sleep(0.02)
    page.toggle()                       # 停止 → settle
    t_end = time.perf_counter()
    while time.perf_counter() - t_end < 1.6:
        app.processEvents()
        time.sleep(0.008)
    TRACE["on"] = False

    # ---- 分析 ----
    print("\n=== 几何变化（按窗口坐标 x 判定水平跳） ===")
    geo_by_widget = {}
    for ts, kind, info in RECORDS:
        if kind != "geo":
            continue
        wid, name, prev, cur = info
        geo_by_widget.setdefault((wid, name), []).append((ts - t0, prev, cur))

    for (wid, name), seq in geo_by_widget.items():
        cxs = [c[0] + c[2] / 2.0 for _, _, c in seq]
        wds = [c[2] for _, _, c in seq]
        if len(set(cxs)) > 1 or len(set(wds)) > 1:
            print(f"  [中心x/宽 变化] {name}")
            for t, prev, cur in seq:
                pc = f"{prev[0]+prev[2]/2:.1f}" if prev else "-"
                cc = f"{cur[0]+cur[2]/2:.1f}" if cur else "-"
                print(f"      t={t*1000:7.1f}ms  {prev} -> {cur}"
                      f"   (中心x {pc} -> {cc})")

    print("\n=== MotionEffect 绘制落点（窗口坐标系里的内容中心 x） ===")
    draws = [r for r in RECORDS if r[1] == "draw"]
    by_widget = {}
    for ts, _, info in draws:
        by_widget.setdefault((info[0], info[1]), []).append((ts - t0, info))
    for (wid, name), seq in by_widget.items():
        print(f"  {name}: {len(seq)} 帧")
        xs = []
        for t, info in seq:
            s, dx, dy, a, bleed, sox, soy, pmsz, wsz = info[2:]
            # 内容中心在控件里的位置：w/2 + dx（缩放不改变中心）
            cx = wsz[0] / 2 + dx
            xs.append((t, cx, s, a))
        if not xs:
            continue
        print("      t(ms) / 中心x / s / a：")
        step = max(1, len(xs) // 12)
        for t, cx, s, a in xs[::step] + [xs[-1]]:
            print(f"      {t*1000:8.1f}  {cx:7.2f}  {s:6.3f}  {a:5.2f}")
        uniq = sorted({round(cx, 1) for _, cx, _, _ in xs})
        print(f"      → 中心 x 取值集合（前 20）：{uniq[:20]}")

    print("\n=== 时间线（几何 + 绘制首末帧） ===")
    evs = [(ts - t0, kind, info) for ts, kind, info in RECORDS]
    evs.sort()
    for t, kind, info in evs[:6]:
        print(f"  {t*1000:8.1f}ms {kind}")
    for t, kind, info in evs[-6:]:
        print(f"  {t*1000:8.1f}ms {kind}")

    win.close()


if __name__ == "__main__":
    main()
