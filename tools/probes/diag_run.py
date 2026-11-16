# -*- coding: utf-8 -*-
"""崩溃/闪退取证：记录主窗口 closeEvent 调用栈、destroyed、aboutToQuit、向导 done。"""
import datetime
import sys
import traceback

sys.path.insert(0, ".")
LOG = "ui_preview/_diag.log"
_f = open(LOG, "w", encoding="utf-8", buffering=1)


def log(msg: str) -> None:
    _f.write(f"{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]} {msg}\n")


# ---- 钩 1：MainWindow 生命周期 ----
import app.ui_main as um

_orig_init = um.MainWindow.__init__


def _init(self, *a, **k):
    _orig_init(self, *a, **k)
    log("MainWindow.__init__ done")
    self.destroyed.connect(lambda *a: log("!! WIN destroyed"))
    _orig_ce = self.closeEvent

    def _ce(ev):
        log("!! WIN closeEvent, stack:\n" + "".join(traceback.format_stack()))
        _orig_ce(ev)

    self.closeEvent = _ce


um.MainWindow.__init__ = _init

# ---- 钩 2：SetupWizard 的 done/reject ----
import app.ui_dialogs as ud

for cls_name in ("SetupWizard", "MaterialDialog"):
    cls = getattr(ud, cls_name, None)
    if cls is None:
        continue
    orig_done = cls.done

    def _make(n, f):
        def _done(self, result, _f=f, _n=n):
            log(f"!! {n}.done({result}), stack:\n" + "".join(traceback.format_stack()))
            return _f(self, result)

        return _done

    cls.done = _make(cls_name, orig_done)

# ---- 钩 3：QWidget.close / closeAllWindows ----
from PySide6.QtWidgets import QWidget as _W, QApplication as _QSA

_orig_wclose = _W.close


def _wclose(self):
    log(f"!! QWidget.close() on {type(self).__name__} id={id(self)}, stack:\n"
        + "".join(traceback.format_stack()))
    return _orig_wclose(self)


_W.close = _wclose

_orig_caw = _QSA.closeAllWindows


def _caw(*a, **k):
    log("!! QApplication.closeAllWindows(), stack:\n" + "".join(traceback.format_stack()))
    return _orig_caw(*a, **k)


_QSA.closeAllWindows = _caw

# ---- 钩 4：应用级事件过滤器，记录所有 Close/Quit 事件 ----
from PySide6.QtCore import QEvent as _QE, QObject as _QO, QTimer as _QT


class _CloseSpy(_QO):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == _QE.Close:
            sp = getattr(ev, "spontaneous", lambda: "?")()
            log(f"!! QEvent.Close -> {type(obj).__name__} id={id(obj)} spontaneous={sp}")
        elif t == _QE.Quit:
            log(f"!! QEvent.Quit -> {type(obj).__name__}")
        elif t == _QE.DeferredDelete:
            log(f"!! QEvent.DeferredDelete -> {type(obj).__name__} id={id(obj)}")
        return False


# ---- 钩 5：QApplication.exec / aboutToQuit ----

_orig_exec = _QSA.exec


def _exec(*a, **k):
    app = a[0] if a and isinstance(a[0], _QSA) else _QSA.instance()
    app.aboutToQuit.connect(lambda: log("!! aboutToQuit"))
    app.lastWindowClosed.connect(lambda: log("!! lastWindowClosed"))
    log("QApplication.exec() enter")
    rc = _orig_exec()
    log(f"QApplication.exec() returned {rc}")
    return rc


_QSA.exec = _exec

# ---- 心跳：每 5 秒记录顶层窗口数 ----
import ctypes

from PySide6.QtCore import QTimer


def _heartbeat():
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "随机抽号")
    log(f"heartbeat: main hwnd={hwnd}")


# 在 app 创建后启动心跳：钩 QApplication 构造
_orig_qapp_init = _QSA.__init__


def _qapp_init(self, *a, **k):
    _orig_qapp_init(self, *a, **k)
    self._spy = _CloseSpy(self)
    self.installEventFilter(self._spy)
    t = _QT(self)
    t.timeout.connect(_heartbeat)
    t.start(5000)
    self._hb = t


_QSA.__init__ = _qapp_init

if __name__ == "__main__":
    from app.main import main

    rc = main()
    log(f"main() returned {rc}")
    print(f"diag exit {rc}", flush=True)
