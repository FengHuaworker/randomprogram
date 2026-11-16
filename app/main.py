# -*- coding: utf-8 -*-
"""
程序入口：
- 正常启动：注册随包字体（Playfair Display / DM Sans）→ 应用莫兰迪主题 →
  显示“圆形呼吸”启动标识 → 创建主窗口并最大化 → 标识优雅消隐；
- --selftest：免界面自检（数据层 + GUI 冒烟），退出码 0 = 通过。
=========================================================================
DPI 说明：Qt6 在 Windows 上默认启用 Per-Monitor V2 高 DPI 感知，
界面所有尺寸使用逻辑像素（px），随系统 125%/150% 缩放自动适配；
此处仅额外声明缩放舍入策略为 PassThrough，保证高分屏文字清晰。
"""

import os
import sys
import traceback


def _crash_path() -> str:
    """崩溃日志固定写到可执行文件/源码根目录（不随工作目录漂移）。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "_crash.txt")


def _log_crash():
    """崩溃日志写到 exe 同目录，console=False 也能看到。"""
    path = _crash_path()

    def _hook(exc_type, exc_val, exc_tb):
        try:
            with open(path, 'a', encoding='utf-8') as f:
                traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
        except Exception:
            pass
    sys.excepthook = _hook

    import faulthandler
    try:
        faulthandler.enable(open(path, 'w'))
    except Exception:
        pass


def _window_icon():
    """加载内置图标（打包后从 _MEIPASS 读取，开发时从项目根读取）。"""
    try:
        from PySide6.QtGui import QIcon
        from pathlib import Path
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        p = base / "assets" / "app_icon.ico"
        if p.exists():
            return QIcon(str(p))
    except Exception:
        pass
    return None


def _asset_root() -> str:
    """资源根目录：打包后 = _MEIPASS；源码运行 = 项目根。"""
    if getattr(sys, "_MEIPASS", None):
        return sys._MEIPASS
    from pathlib import Path
    return str(Path(__file__).resolve().parent.parent)


# 顶层窗口的强引用表。PySide6 的 QWidget 若失去全部 Python 引用，包装对象被
# GC 时会连 C++ 窗口一起销毁 → 窗口无故闪退；残留的 QTimer/动画再访问已销毁
# 对象即段错误（faulthandler 也未必来得及落盘）。此前 _boot() 里 win 只是局部
# 变量，boot 一返回就满足 GC 条件——这就是反复“闪退/崩了”但日志全空的根因。
_APP_WINDOWS: list = []


def main() -> int:
    _log_crash()          # 一进来就挂崩溃钩子（此前漏调用，崩了无迹可查）

    if "--selftest" in sys.argv:
        # 自检不需要显示器（打包后的 exe 也可在无人值守下验证）
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    from pathlib import Path

    # 高 DPI 缩放舍入策略：PassThrough（Qt6 默认已开启 DPI 感知）
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("随机抽号")

    from . import theme
    # 注册随包字体（必须在 QApplication 创建之后）
    theme.register_fonts(_asset_root())
    theme.apply_theme(app)

    if "--selftest" in sys.argv:
        from .selftest import run_selftest
        return run_selftest(app)

    from .ui_main import MainWindow
    from .app_data import ClassManager
    from .ui_widgets import SplashWindow

    icon = _window_icon()
    if icon:
        app.setWindowIcon(icon)

    # —— 启动标识：莫兰迪圆形呼吸，随后优雅消隐 ——
    splash = SplashWindow()
    _APP_WINDOWS.append(splash)               # 强引用，防 GC 闪退
    splash.show_breath()
    app.processEvents()

    def _boot():
        win = MainWindow(ClassManager())
        _APP_WINDOWS.append(win)              # 强引用到进程结束（关键）
        if icon:
            win.setWindowIcon(icon)
        win.showMaximized()
        app.processEvents()
        splash.finish()                       # 标识淡出
        QTimer.singleShot(520, win.startup)   # 等标识消隐后再弹配置向导

    QTimer.singleShot(1250, _boot)            # 让呼吸动画完整展示一会儿
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
