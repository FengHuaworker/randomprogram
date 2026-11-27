# -*- coding: utf-8 -*-
"""悬浮球真实鼠标事件测试：单击、双击、长按拖动、前台屏蔽。"""

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
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.app_data import ClassManager  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402
from app.ui_float import FloatDock  # noqa: E402
from app import app_data  # noqa: E402


def pump(app, ms=120):
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.004)


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{detail}]" if detail else ""))
    if not cond:
        raise AssertionError(label)


def move_event(widget, local, global_pt):
    return QMouseEvent(QMouseEvent.MouseMove, QPointF(local), QPointF(global_pt),
                       QPointF(global_pt), Qt.NoButton, Qt.LeftButton,
                       Qt.NoModifier)


def main():
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    (ROOT / ".tmp").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="float_input_", dir=str(ROOT / ".tmp")))
    try:
        mgr = ClassManager(tmp)
        mgr.ensure_dirs(); mgr.ensure_template()
        name = mgr.create_class("输入测试")
        st = mgr.get_class(name)
        st.roster_write([f"同学{i}" for i in range(1, 21)])
        cfg = st.load_config(); cfg["total_count"] = 20; st.save_config(cfg)

        win = MainWindow(mgr)
        win.resize(1000, 700)
        win.show(); app.processEvents()
        win._reload_class(name); app.processEvents()
        win.hide(); pump(app)

        dock = FloatDock(win, enable_tray=False)
        dock.ready = True
        dock.user_visible = True
        dock.ball.move(0, 240)
        dock.ball._rest_pos = dock.ball.pos()
        dock.ball.show_in(animate=False)
        pump(app, 80)
        ball = dock.ball
        center = QPoint(ball.width() // 2, ball.height() // 2)

        # 1) 单击展开
        QTest.mouseClick(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 240)
        check("单击展开卡片", dock.card.is_open)

        # 2) 单击收起
        QTest.mouseClick(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 360)
        check("再单击收起卡片", not dock.card.is_open)

        # 3) 双击直接全屏抽号（第一击不会留下展开的卡片）
        QTest.mouseDClick(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 140)
        check("双击启动全屏抽号", dock.overlay.active)
        check("双击后卡片不残留", not dock.card.is_open)
        check("全屏时球已收起", not ball.isVisible() or ball.is_hiding())
        dock.overlay.stop_now()
        pump(app, 260)

        # 4) 长按拖动：按住 420ms 后移动，松手吸附到边缘
        start_pos = ball.pos()
        QTest.mousePress(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 430)
        check("长按进入拖拽", ball._dragging)
        gp = ball.mapToGlobal(center) + QPoint(0, 90)
        ev = move_event(ball, QPoint(center.x(), center.y() + 90), gp)
        ball.mouseMoveEvent(ev)
        pump(app, 60)
        moved_y = ball.y()
        check("拖拽确实移动了窗口", abs(moved_y - start_pos.y()) > 40,
              f"{start_pos.y()} -> {moved_y}")
        QTest.mouseRelease(ball, Qt.LeftButton, Qt.NoModifier,
                           QPoint(center.x(), center.y() + 90))
        pump(app, 360)
        scr = dock.screen_at(ball.geometry().center())
        avail = scr.availableGeometry()
        near_left = abs(ball.x() - avail.left()) <= 1
        near_right = abs(ball.x() - (avail.right() - ball.width() + 1)) <= 1
        check("松手吸附到边缘", near_left or near_right, f"x={ball.x()}")
        check("拖拽后不误触卡片", not dock.card.is_open)

        # 5) 主窗口在前台时，球不接收任何操作
        QTest.mouseClick(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 260)
        dock.card.close(instant=True)
        old = dock.main_active
        dock.main_active = lambda: True
        QTest.mouseClick(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 240)
        check("主窗口前台时单击无效", not dock.card.is_open)
        QTest.mouseDClick(ball, Qt.LeftButton, Qt.NoModifier, center)
        pump(app, 120)
        check("主窗口前台时双击无效", not dock.overlay.active)
        dock.main_active = old

        print("\nALL PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
