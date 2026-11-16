# -*- coding: utf-8 -*-
"""定格序列细粒度时间线：定位停止时的单帧大卡顿（173ms）花在哪个环节。
用法：python tools/frame_timeline.py
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

tmp = Path(tempfile.mkdtemp(prefix="rp_tl_"))
src = ROOT / "发布版" / "classes"
if src.exists():
    shutil.copytree(src, tmp / "classes")
else:
    (tmp / "classes" / "默认班级").mkdir(parents=True)

from app.app_data import ClassManager
from app.ui_main import MainWindow

mgr = ClassManager(tmp)
mgr.ensure_dirs()
win = MainWindow(mgr)
win.setWindowTitle("TIMELINE")
win.showMaximized()
win.startup()
app.processEvents()
for _ in range(80):
    app.processEvents()
    if win.store is not None:
        break
time.sleep(0.5)
app.processEvents()

dp = win.draw_page

# ---------------- 事件时间线 ----------------
T0 = [0.0]
events = []      # (t_ms, kind, detail)


def mark(kind, detail=""):
    events.append(((time.perf_counter() - T0[0]) * 1000, kind, detail))


class Tap(QObject):
    def eventFilter(self, obj, event):
        if T0[0] and event.type() == QEvent.Paint:
            try:
                r = event.rect()
                name = obj.objectName() or type(obj).__name__
                events.append(((time.perf_counter() - T0[0]) * 1000,
                               "paint", f"{name} {r.width()}x{r.height()}"))
            except Exception:
                pass
        return False


tap = Tap()
app.installEventFilter(tap)

# 包裹关键调用
import app.motion as motion
_orig_burst = motion.BurstOverlay.__init__


def timed_burst(self, target, color, max_r=160, dur=620):
    mark("burst.create", f"max_r={max_r} dur={dur}")
    t0 = time.perf_counter()
    _orig_burst(self, target, color, max_r=max_r, dur=dur)
    mark("burst.created", f"{(time.perf_counter()-t0)*1000:.1f}ms")


motion.BurstOverlay.__init__ = timed_burst

_orig_refresh_pool = dp._refresh_pool


def timed_pool():
    mark("pool.begin")
    t0 = time.perf_counter()
    _orig_refresh_pool()
    mark("pool.end", f"{(time.perf_counter()-t0)*1000:.1f}ms")


dp._refresh_pool = timed_pool

_orig_record = dp.store.record_draws


def timed_record(draws, mode, anti_dup=True):
    t0 = time.perf_counter()
    _orig_record(draws, mode, anti_dup=anti_dup)
    mark("record_draws", f"{(time.perf_counter()-t0)*1000:.1f}ms")


dp.store.record_draws = timed_record

_orig_roll_to = dp.num_label.roll_to


def timed_roll_to(text, dur=560):
    mark("roll_to", text)
    _orig_roll_to(text, dur)


dp.num_label.roll_to = timed_roll_to

# ---------------- 跑场景 ----------------
dp.start()
app.processEvents()
t_end = time.perf_counter() + 1.2
while time.perf_counter() < t_end:
    app.processEvents()
    time.sleep(0.002)
app.processEvents()

events.clear()
T0[0] = time.perf_counter()
mark("=== STOP 按下 ===")
dp.stop()
t_end = time.perf_counter() + 1.6
while time.perf_counter() < t_end:
    app.processEvents()
    time.sleep(0.002)
app.processEvents()

# ---------------- 分析输出 ----------------
print("=" * 78)
print("停止后 1.6s 时间线（仅关键事件 + 相邻 paint 间隔 >20ms 的帧）")
print("=" * 78)
prev_t = 0.0
prev_kind = ""
for t, kind, detail in events:
    gap = t - prev_t
    if kind in ("burst.create", "burst.created", "pool.begin", "pool.end",
                "record_draws", "roll_to", "=== STOP 按下 ===") or gap > 20:
        print(f"{t:8.1f}ms  +{gap:6.1f}  {kind:16s} {detail}")
    prev_t = t
    prev_kind = kind

# 帧间隔统计（paint 批次）
paints = [e for e in events if e[1] == "paint"]
if paints:
    batches = [[paints[0]]]
    for p in paints[1:]:
        if p[0] - batches[-1][-1][0] < 0.006:
            batches[-1].append(p)
        else:
            batches.append([p])
    ivs = [(batches[i + 1][0][0] - batches[i][0][0]) for i in range(len(batches) - 1)]
    print()
    print("帧间隔序列(ms):", " ".join(f"{v:.0f}" for v in ivs))
    print(f"最大帧间隔 = {max(ivs):.0f}ms")

app.quit()
