# -*- coding: utf-8 -*-
"""真实窗口帧探针：测量切页 / 抽号定格过程中的帧间隔与每帧绘制耗时。
在真实 Windows 合成器下运行（不用 offscreen），可复现用户感知的卡顿。
用法：python tools/frame_probe.py [--before|--after]
输出：帧间隔序列 + 卡顿帧统计 + 每帧绘制 CPU。
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 不使用 offscreen：要真实合成器

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

tmp = Path(tempfile.mkdtemp(prefix="rp_frame_"))
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
win.setWindowTitle("FRAME PROBE")
win.showMaximized()
win.startup()
app.processEvents()
for _ in range(80):
    app.processEvents()
    if win.store is not None:
        break
app.processEvents()
time.sleep(0.6)
app.processEvents()

# ---------------- 帧记录 ----------------
LOG = []          # (t, widget_class, rect_area)
_recording = {"on": False, "tag": ""}
BATCH_GAP = 0.006  # >6ms 视为新的一帧


class PaintTap(QObject):
    def eventFilter(self, obj, event):
        if _recording["on"] and event.type() == QEvent.Paint:
            try:
                r = event.rect()
                LOG.append((time.perf_counter(), type(obj).__name__,
                            max(0, r.width()) * max(0, r.height())))
            except Exception:
                pass
        return False


tap = PaintTap()
app.installEventFilter(tap)


def drain(seconds):
    """跑一段时间事件循环，返回本段记录数。"""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        app.processEvents()
        time.sleep(0.001)


def run_phase(tag, seconds):
    _recording["tag"] = tag
    LOG.clear()
    _recording["on"] = True
    drain(seconds)
    _recording["on"] = False
    return analyze(tag)


def analyze(tag):
    if len(LOG) < 2:
        print(f"[{tag}] 采样不足: {len(LOG)}")
        return None
    # 分批：间隔 <BATCH_GAP 的 paint 归为同一帧
    batches = []
    cur = [LOG[0]]
    for rec in LOG[1:]:
        if rec[0] - cur[-1][0] < BATCH_GAP:
            cur.append(rec)
        else:
            batches.append(cur)
            cur = [rec]
    batches.append(cur)
    starts = [b[0][0] for b in batches]
    intervals = [(starts[i + 1] - starts[i]) * 1000 for i in range(len(starts) - 1)]
    paint_cpu = [(b[-1][0] - b[0][0]) * 1000 for b in batches]
    n = len(intervals)
    avg = sum(intervals) / max(1, n)
    worst = max(intervals) if intervals else 0
    jank = sum(1 for v in intervals if v > 25)
    heavy = sum(1 for v in paint_cpu if v > 12)
    print(f"[{tag}] 帧数={len(batches):3d}  平均帧间隔={avg:5.1f}ms  "
          f"最大={worst:6.1f}ms  卡顿帧(>25ms)={jank:2d}  重帧(绘制>12ms)={heavy:2d}  "
          f"绘制CPU中位={sorted(paint_cpu)[len(paint_cpu)//2]:5.1f}ms")
    return intervals, paint_cpu


def click(w):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF
    pos = QPointF(w.rect().center())
    for typ in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        ev = QMouseEvent(typ, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(w, ev)
    app.processEvents()


# ---------------- 场景 ----------------
# 1) 基线（静止）
run_phase("基线(静止)", 1.0)

# 2) 切到抽号页（从历史页切回）
win.stack.setCurrentIndex(1)
app.processEvents()
run_phase("准备-历史页", 0.4)
nav = win.nav
# 通过导航按钮切回抽号页
idx0_btn = None
for b in nav.findChildren(type(nav)):
    pass
# 直接调用切页逻辑（与点击导航等价）
LOG.clear()
_recording["on"] = True
win._on_nav_changed(0)
drain(1.0)
_recording["on"] = False
analyze("切到抽号页(动画)")

# 3) 开始抽号 → 滚动 1.2s → 停止 → 定格序列
run_phase("准备-停止态", 0.3)
win.draw_page.start()
app.processEvents()
run_phase("抽号滚动中", 1.0)

LOG.clear()
_recording["on"] = True
win.draw_page.stop()
drain(2.0)
_recording["on"] = False
analyze("停止定格序列")

# 4) 再切走再切回
LOG.clear()
_recording["on"] = True
win._on_nav_changed(2)
drain(0.35)
win._on_nav_changed(0)
drain(1.0)
_recording["on"] = False
analyze("统计页→抽号页")

print("\n临时目录:", tmp)
app.quit()
