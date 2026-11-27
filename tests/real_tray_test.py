# -*- coding: utf-8 -*-
"""真实 Windows 桌面下的托盘/关闭/前台隐藏冒烟（会短暂弹窗）。"""

import sys, os, time, tempfile, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtWidgets import QApplication
from app import theme, app_data
from app.app_data import ClassManager
from app.ui_main import MainWindow
from app.ui_float import FloatDock


def pump(app, ms=120):
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.004)


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{detail}]" if detail else ""))
    if not cond:
        raise AssertionError(label)


def main():
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    (ROOT / ".tmp").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="real_tray_", dir=str(ROOT / ".tmp")))
    try:
        mgr = ClassManager(tmp)
        mgr.ensure_dirs(); mgr.ensure_template()
        name = mgr.create_class("托盘测试班")
        st = mgr.get_class(name)
        st.roster_write(["甲","乙","丙","丁","戊","己","庚","辛"])
        cfg = st.load_config(); cfg["total_count"] = 8; st.save_config(cfg)

        win = MainWindow(mgr)
        win.resize(960, 640)
        win.show()
        app.processEvents()
        win._reload_class(name)
        app.processEvents()

        dock = FloatDock(win)
        win.float_dock = dock
        dock.ready = True
        dock.activate()
        pump(app, 320)

        check("托盘图标已创建", dock.tray is not None and dock.tray.isVisible())
        check("托盘菜单三项齐全", all(a is not None for a in (dock.act_open, dock.act_ball, dock.act_quit)))

        win.raise_(); win.activateWindow()
        pump(app, 450)
        active = win.isActiveWindow()
        check("主窗口获得焦点", active, str(active))
        check("主窗口前台时球自动隐藏", not dock.ball.isVisible() and not dock.ball.is_hiding())

        # 关闭 -> 托盘
        win.close()
        pump(app, 300)
        check("关闭后主窗隐藏", not win.isVisible())
        check("关闭后托盘仍在", dock.tray.isVisible())
        check("关闭后球回到桌面", dock.ball.isVisible() or dock.ball.is_hiding())

        # 托盘打开主窗
        dock.act_open.trigger()
        pump(app, 450)
        check("托盘能重新打开主窗", win.isVisible())
        check("主窗在前台时球又收起", not dock.ball.isVisible() or dock.ball.is_hiding())

        # 托盘隐藏球
        dock.act_ball.setChecked(False)
        pump(app, 320)
        check("托盘可关闭悬浮球", not dock.ball.isVisible() and not dock.ball.is_hiding())
        dock.act_ball.setChecked(True)
        win.hide()
        pump(app, 620)
        check("托盘可恢复悬浮球", dock.ball.isVisible())

        # 双击抽一个，真实动画跑完
        dock.user_visible = True
        dock.ball.show_in(animate=False)
        pump(app, 80)
        dock.quick_draw()
        ok = dock.overlay.active
        check("真实桌面全屏抽号启动", ok)
        steps = int(4.2 / 0.05)
        for _ in range(steps):
            pump(app, 50)
        check("动画结束后压暗层关闭", not dock.overlay.active)
        check("动画结束后球恢复", dock.ball.isVisible())
        check("本轮记录已写入", len(win.store.round_list()) == 1)

        dock.quit_app()
        pump(app, 300)
        check("退出后托盘隐藏", dock.tray is None or not dock.tray.isVisible())
        print("\nALL PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        app_data.flush()


if __name__ == "__main__":
    main()
