# -*- coding: utf-8 -*-
"""悬浮球/托盘交互的自动化冒烟测试（离屏，不弹窗）。

覆盖：卡片开合、空白区开始/结束、记录与主界面统一、重置二次确认、
全屏层落盘、关闭到托盘、状态文件、拖拽吸附。
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QEvent, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402
from app.ui_float import FloatDock  # noqa: E402
from app import app_data  # noqa: E402

NAMES = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸", "子", "丑"]


def pump(app, ms=120):
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{detail}]" if detail else ""))
    if not cond:
        raise AssertionError(label)


def mouse(widget, typ, pos):
    gp = widget.mapToGlobal(QPoint(int(pos.x()), int(pos.y())))
    ev = QMouseEvent(typ, pos, QPointF(gp), QPointF(gp),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    return ev


def main():
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    (ROOT / ".tmp").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="float_test_", dir=str(ROOT / ".tmp")))
    try:
        mgr = ClassManager(tmp)
        mgr.ensure_dirs()
        mgr.ensure_template()
        name = mgr.create_class("测试班")
        st = mgr.get_class(name)
        st.roster_write(NAMES)
        cfg = st.load_config()
        cfg["mode"] = MODE_ADVANCED
        cfg["total_count"] = len(NAMES)
        st.save_config(cfg)

        win = MainWindow(mgr)
        win.resize(1100, 720)
        win.show()
        app.processEvents()
        win._reload_class(name)
        app.processEvents()
        win.hide()                      # 让 main_active 为假，球可操作
        pump(app)

        dock = FloatDock(win, enable_tray=False)
        dock.ready = True
        dock.user_visible = True
        dock.ball.show_in(animate=False)
        pump(app, 60)

        check("初始 store 已就绪", win.store is not None)
        check("初始本轮为 0", len(win.store.round_list()) == 0)

        # 1) 单击展开 / 收起
        dock.toggle_card()
        pump(app, 60)
        check("单击展开卡片", dock.card.is_open and dock.card.isVisible())
        dock.toggle_card()
        pump(app, 260)
        check("再单击收起卡片", not dock.card.is_open)

        # 2) 空白区开始/结束，记录写进同一个 store
        dock.toggle_card()
        pump(app, 340)
        card = dock.card
        card._reveal = 1.0
        n0 = len(win.store.round_list())
        before_hist = len(win.store.history())
        card.toggle_draw()
        check("点空白开始抽号", card._running)
        pump(app, 120)
        card.toggle_draw()
        pump(app, 60)
        check("再点空白结束抽号", not card._running)
        check("本轮记录 +1", len(win.store.round_list()) == n0 + 1,
              str(len(win.store.round_list())))
        check("历史记录 +1", len(win.store.history()) == before_hist + 1,
              str(len(win.store.history())))
        check("卡片计数同步", card._count == n0 + 1, str(card._count))
        check("卡片显示结果", card._state == "result" and bool(card._num))

        pump(app, 260)                  # 等 80ms 的延迟刷新
        check("主界面抽号页同步到最后结果",
              win.draw_page.num_label.text() == card._num,
              f"{win.draw_page.num_label.text()} vs {card._num}")

        # 3) 重置：第一次只进入确认态，第二次才真正清空
        before_reset = len(win.store.round_list())
        card.arm_reset()
        check("重置第一次不执行", len(win.store.round_list()) == before_reset)
        check("重置进入确认态", card._reset_until > time.perf_counter())
        card.arm_reset()
        pump(app, 80)
        check("重置第二次清空本轮", len(win.store.round_list()) == 0)
        check("重置后卡片归零", card._count == 0 and card._state == "empty")
        check("重置保留历史", len(win.store.history()) == before_hist + 1)

        # 4) 全屏层：落定写记录，结束后恢复
        dock.user_visible = True
        dock.ball.show_in(animate=False)
        pump(app, 60)
        ok = dock.overlay.play()
        check("全屏抽号启动", ok and dock.overlay.active)
        check("全屏层覆盖所有屏幕", len(dock.overlay.wins) >= 1)
        # 直接把时钟拨到落定点，触发 _tick 内的落盘
        dock.overlay._t0 = time.perf_counter() - 1.7
        dock.overlay._tick()
        pump(app, 40)
        check("全屏层写入本轮", len(win.store.round_list()) == 1,
              str(len(win.store.round_list())))
        check("全屏层写入历史", len(win.store.history()) == before_hist + 2,
              str(len(win.store.history())))
        check("全屏层脚注有计数", dock.overlay._record_n == 1)
        dock.overlay.stop_now()
        pump(app, 100)
        check("全屏层已关闭", not dock.overlay.active and not dock.overlay.wins)

        # 5) 拖拽吸附：松手后一定回到左右边缘
        dock.ball.move(260, 220)
        dock.ball._rest_pos = dock.ball.pos()
        dock.ball.snap_to_edge(animate=False)
        scr = dock.screen_at(dock.ball.geometry().center())
        avail = scr.availableGeometry()
        near_left = abs(dock.ball.x() - avail.left()) <= 1
        near_right = abs(dock.ball.x() - (avail.right() - dock.ball.width() + 1)) <= 1
        check("拖拽后吸附到边缘", near_left or near_right, f"x={dock.ball.x()}")
        dock.save_state()
        check("悬浮球状态已写盘", (tmp / "float_state.json").exists())
        raw = (tmp / "float_state.json").read_text(encoding="utf-8")
        check("状态文件含显隐字段", '"visible"' in raw)

        # 6) 关闭主窗口 = 收进托盘（没有托盘时则真正关闭）
        win.show()
        pump(app, 80)
        win.close()
        pump(app, 60)
        check("关闭主窗口后进程仍在（窗口隐藏）", not win.isVisible())
        win.show_main()
        pump(app, 60)
        check("show_main 能重新显示", win.isVisible())

        # 7) 托盘勾选逻辑（无托盘也走同一状态机）
        dock._toggle_from_tray(False)
        pump(app, 320)
        check("关闭悬浮球后不可见", not dock.ball.isVisible())
        dock._toggle_from_tray(True)
        win.hide()                       # 主窗在前台时球按设计不出现，先让出前台
        pump(app, 620)
        check("重新打开悬浮球", dock.ball.isVisible())

        # 8) 退出标记
        win._force_quit = True
        win.close()
        check("强制退出会真正关闭窗口", not win.isVisible())

        app_data.flush()
        print("\nALL PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
