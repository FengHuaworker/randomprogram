# -*- coding: utf-8 -*-
"""性能探针：量化「切到抽号页」与「停止定格」各环节的渲染开销。

测量项：
1. 各区域 grab() 耗时（= QGraphicsEffect 每帧 sourcePixmap 的真实渲染成本）
2. MotionEffect 动画期间 sourcePixmap 被调用的次数（判断 Qt 是否每帧重渲染子树）
3. 定格序列（bounce + burst + 刷新池）主线程阻塞时长
用法：python tools/perf_probe.py
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from app import theme
theme.register_fonts(str(ROOT))
theme.apply_theme(app)

# ---- 用真实数据的副本建一个临时环境（不碰线上数据） ----
tmp = Path(tempfile.mkdtemp(prefix="rp_perf_"))
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
win.resize(1440, 860)
win.show()
app.processEvents()
win._reload_class = getattr(win, "_reload_class", None)

# 等启动流程把第一个班级装上
for _ in range(50):
    app.processEvents()
    if win.store is not None:
        break

dp = win.draw_page
win.stack.setCurrentIndex(0)
dp.refresh()
app.processEvents()
# 手动触发一次 stretch，保证布局尺寸是真实状态
dp._stretch_grid()
app.processEvents()

report = []


def bench(name, fn, n=8):
    fn()  # 预热
    t = QElapsedTimer()
    best = 10**9
    tot = 0
    for _ in range(n):
        t.start()
        fn()
        ms = t.nsecsElapsed() / 1e6
        best = min(best, ms)
        tot += ms
    report.append((name, best, tot / n))
    return best


# 1) grab 成本
bench("draw_page.grab()  整页", lambda: dp.grab())
bench("hero.grab()       主卡片", lambda: dp.hero.grab())
bench("batch_card.grab() 批量卡", lambda: dp.batch_card.grab())
bench("rail.grab()       右栏(两列表)", lambda: dp.rail.grab())
bench("result.grab()     舞台", lambda: dp.result.grab())
bench("num_label.grab()  大数字", lambda: dp.num_label.grab())
bench("pool_list.grab()  池列表(55行)", lambda: dp.pool_list.grab())

# 2) sourcePixmap 调用次数：动画期间是否每帧重渲染子树
import app.motion as motion

orig_draw = motion.MotionEffect.draw
calls = {"n": 0, "frames": 0}
_orig_sp = motion.MotionEffect.sourcePixmap if hasattr(motion.MotionEffect, "sourcePixmap") else None


def counting_draw(self, painter):
    calls["n"] += 1
    return orig_draw(self, painter)


motion.MotionEffect.draw = counting_draw

from PySide6.QtCore import QVariantAnimation, QTimer


def run_anim_and_count(widget, dur=400):
    calls["n"] = 0
    calls["frames"] = 0
    eff = widget.graphicsEffect()
    done = {"v": False}

    anim = QVariantAnimation()
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(dur)
    anim.valueChanged.connect(lambda v: (
        setattr(eff, "s", 0.9 + 0.1 * float(v)),
        setattr(eff, "dx", 8.0 * (1.0 - float(v))),
        eff.update(),
        calls.__setitem__("frames", calls["frames"] + 1)))
    anim.finished.connect(lambda: done.__setitem__("v", True))
    anim.start()
    t0 = time.perf_counter()
    while not done["v"] and time.perf_counter() - t0 < (dur / 1000) + 2:
        app.processEvents()
        time.sleep(0.002)
    app.processEvents()
    return calls["frames"], calls["n"]


motion.MotionEffect.draw = orig_draw

# 3) 定格序列主线程阻塞：模拟 _do_settle 的组合
import random


def settle_cost():
    dp.num_label.set_now("42")
    dp.name_label.setText("测试同学")
    t0 = time.perf_counter()
    # 与 _do_settle 相同的组合
    motion.bounce(dp.num_label, s=1.24, dur=640, rot=-0.6)
    motion.burst(dp.result, theme.COLORS["primary"], max_r=190, dur=760)
    from app.ui_widgets import SealMark  # noqa
    # seal.stamp() 已由动画驱动，这里只测 burst+bounce 组合的帧成本
    frames = 0
    t_end = t0 + 0.8
    while time.perf_counter() < t_end:
        app.processEvents()
        time.sleep(0.002)
        frames += 1
    return time.perf_counter() - t0, frames


# 4) 页面切换当前实现的开销：fade_slide_in(整页 effect) + stagger(三卡 effect)
def page_switch_cost():
    from app.ui_widgets import fade_slide_in
    from app.motion import stagger as m_stagger
    t0 = time.perf_counter()
    win.stack.setCurrentIndex(1)
    app.processEvents()
    win.stack.setCurrentIndex(0)
    app.processEvents()
    fade_slide_in(dp, dx=0, dy=28, dur=380, delay=10)
    m_stagger([dp.hero, dp.batch_card, dp.rail], gap=80, dy=18, s=0.975,
              dur=500, delay=80)
    t_end = t0 + 0.9
    n = 0
    while time.perf_counter() < t_end:
        app.processEvents()
        time.sleep(0.002)
        n += 1
    return time.perf_counter() - t0, n


# ---- 输出 ----
print("=" * 66)
print("渲染成本（单次，毫秒，取 8 次最优/均值）")
print("=" * 66)
for name, best, avg in report:
    print(f"{name:34s} best={best:7.2f}  avg={avg:7.2f}")

print()
print("=" * 66)
print("定格序列（bounce 数字 + 光环 burst）")
print("=" * 66)
el, fr = settle_cost()
print(f"总时长={el*1000:.0f}ms  processEvents 次数={fr}")

print()
print("=" * 66)
print("页面切换（当前实现：整页 opacity + 三卡 MotionEffect）")
print("=" * 66)
el2, fr2 = page_switch_cost()
print(f"总时长={el2*1000:.0f}ms  processEvents 次数={fr2}")

print()
print("临时数据目录:", tmp)
