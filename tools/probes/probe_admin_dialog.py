# -*- coding: utf-8 -*-
"""
探针：渲染管理员密码相关的三个弹窗，检查布局与换行。
输出到 tools/_shots/admin_*.png，用于人工比对（不参与打包）。

用法：python tools/probes/probe_admin_dialog.py
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402

from app import theme, security  # noqa: E402
from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402
from app.ui_dialogs import AdminPasswordDialog, AdminChangeDialog, AppSettingsDialog  # noqa: E402

OUT = ROOT / "tools" / "_shots"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\simsun.ttc")
    theme.apply_theme(app)

    tmp = Path(tempfile.mkdtemp(prefix="probe_admin_"))
    host = QWidget()
    host.resize(1180, 760)
    host.show()
    app.processEvents()

    # 弹窗有入场动画（卡片 660ms + 元素错落 480ms），截图统一等 1.6s，
    # 否则抓到的是半透明中间帧，标题看起来像「消失了」。
    def shoot(widget, tag, gap=1600):
        QTimer.singleShot(gap, lambda: widget.grab().save(str(OUT / f"{tag}.png")))

    d1 = AdminPasswordDialog(host, tmp)          # 首次：设置密码（两框）
    d1.show()
    shoot(d1, "admin_first")
    QTimer.singleShot(1900, d1.close)

    def show_verify():
        security.set_password(tmp, "1234")
        d2 = AdminPasswordDialog(host, tmp)      # 已设置：验证（一框）
        d2.show()
        shoot(d2, "admin_verify", 1500)
        QTimer.singleShot(1800, d2.close)

    QTimer.singleShot(2100, show_verify)

    def show_change():
        d3 = AdminChangeDialog(host, tmp)        # 修改（三框）
        d3.show()
        shoot(d3, "admin_change", 1600)
        QTimer.singleShot(1900, d3.close)

    QTimer.singleShot(4200, show_change)

    def show_settings():
        mgr = ClassManager(tmp)
        mgr.ensure_dirs()
        mgr.ensure_template()
        name = mgr.create_class("三年级1班")
        st = mgr.get_class(name)
        st.roster_write(["甲", "乙", "丙", "丁"])
        cfg = st.load_config()
        cfg["mode"] = MODE_ADVANCED
        cfg["total_count"] = 4
        st.save_config(cfg)
        d4 = AppSettingsDialog(host, st, cfg)
        d4.show()
        shoot(d4, "admin_settings", 1700)
        QTimer.singleShot(2000, d4.close)

    QTimer.singleShot(6400, show_settings)

    QTimer.singleShot(8800, app.exit)
    app.exec()
    shutil.rmtree(tmp, ignore_errors=True)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
