# -*- coding: utf-8 -*-
"""布局审计：在指定缩放/窗口尺寸下输出各区域几何，便于发现遮挡。"""

import os
import sys
import json
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app import theme  # noqa: E402
from app.ui_main import MainWindow  # noqa: E402

W = int(os.environ.get("AUDIT_W", "960"))
H = int(os.environ.get("AUDIT_H", "540"))
TAG = os.environ.get("AUDIT_TAG", "audit")

app = QApplication(sys.argv)
QFontDatabase.addApplicationFont("C:/Windows/Fonts/simsun.ttc")
theme.apply_theme(app)

tmp = Path(tempfile.mkdtemp())
mgr = ClassManager(tmp)
mgr.ensure_dirs()
name = mgr.create_class("审计班")
st = mgr.get_class(name)
st.roster_write([f"学生{i}" for i in range(1, 19)])
cfg = st.load_config()
cfg["mode"] = MODE_ADVANCED
cfg["total_count"] = 18
st.save_config(cfg)
st.record_draws([{"num": 3, "name": "学生3"}], MODE_ADVANCED, anti_dup=True)

win = MainWindow(mgr)
win.resize(W, H)
win.show()
win._reload_class(name)
QTest.qWait(800)

dp = win.draw_page


def rect(w):
    g = w.geometry()
    return [g.x(), g.y(), g.width(), g.height()]


data = {
    "window": [win.width(), win.height()],
    "topbar": rect(win.centralWidget().findChild(QWidget, "TopBar")),
    "stack": rect(win.stack),
    "nav": rect(win.nav),
    "nav_h": win.nav.height(),
    "draw": [dp.width(), dp.height()],
    "scroll_viewport": [dp.scroll.viewport().width(), dp.scroll.viewport().height()],
    "content": [dp.content.width(), dp.content.height()],
    "hero": rect(dp.hero),
    "rail": rect(dp.rail),
    "result": rect(dp.result),
    "num": rect(dp.num_label),
    "btn_toggle": rect(dp.btn_toggle),
    "btn_toggle_min": dp.btn_toggle.minimumHeight(),
    "btn_toggle_hint": dp.btn_toggle.sizeHint().height(),
    "btn_batch": rect(dp.btn_batch),
    "wide": dp._wide,
    "num_px": dp.num_label.font().pixelSize(),
}

# 越界检查：子控件是否超出父控件
def overflow(child, parent):
    cg, pg = child.geometry(), parent.rect()
    return (cg.right() > pg.right() + 1 or cg.bottom() > pg.bottom() + 1
            or cg.left() < -1 or cg.top() < -1)


checks = {
    "hero_overflow": overflow(dp.hero, dp.content),
    "rail_overflow": overflow(dp.rail, dp.content),
    "num_overflow": overflow(dp.num_label, dp.result),
    "batch_btn_overflow": overflow(dp.btn_batch, dp.hero),
    "nav_overflow": overflow(win.nav, win.centralWidget()),
}
data["checks"] = checks
Path(ROOT / "ui_preview" / f"_{TAG}.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
win.grab().save(str(ROOT / "ui_preview" / f"_{TAG}.png"))
print(json.dumps(data, ensure_ascii=False))
