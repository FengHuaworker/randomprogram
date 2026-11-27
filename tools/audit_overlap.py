# -*- coding: utf-8 -*-
"""通用遮挡审计：找「两个可见叶子控件互相压住」和「子控件超出父控件被裁」。

判定规则（尽量少误报）：
- 只比较叶子控件（QLabel / QPushButton / QLineEdit / QComboBox / QSpinBox /
  自定义绘制控件），容器不参与；
- 祖孙关系、或一方是 QComboBox/QAbstractSpinBox 这种「外壳自带子控件」的
  ��不比较；
- 相交面积 > 6 平方像素才报。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QLineEdit,
                               QComboBox, QAbstractSpinBox, QAbstractButton,
                               QAbstractItemView, QScrollBar, QCheckBox, QRadioButton)

LEAF = (QLabel, QPushButton, QLineEdit, QComboBox, QAbstractSpinBox, QAbstractButton,
        QAbstractItemView)
SKIP_PARENT = (QComboBox, QAbstractSpinBox, QAbstractItemView)


def rect_in(w, top):
    p = w.mapTo(top, QPoint(0, 0))
    return QRect(p, w.size())


def is_ancestor(a, b):
    p = b.parentWidget()
    while p is not None:
        if p is a:
            return True
        p = p.parentWidget()
    return False


def audit(root, name):
    leaves = []
    for w in root.findChildren(QWidget):
        if not w.isVisible() or w.width() < 4 or w.height() < 4:
            continue
        # 640x480 是 QWidget 出生尺寸：控件还没参与布局，几何无意义，不能当遮挡
        if w.width() == 640 and w.height() == 480:
            continue
        if isinstance(w, (QScrollBar,)):
            continue
        if not isinstance(w, LEAF):
            continue
        leaves.append(w)
    issues = []
    for i, a in enumerate(leaves):
        for b in leaves[i + 1:]:
            if is_ancestor(a, b) or is_ancestor(b, a):
                continue
            if isinstance(a.parentWidget(), SKIP_PARENT) or isinstance(b.parentWidget(), SKIP_PARENT):
                continue
            ra, rb = rect_in(a, root), rect_in(b, root)
            inter = ra.intersected(rb)
            if inter.width() > 2 and inter.height() > 2 and inter.width() * inter.height() > 6:
                issues.append((a, b, ra, rb, inter))
    # 子控件超出父控件
    clipped = []
    for w in root.findChildren(QWidget):
        if not w.isVisible() or isinstance(w, (QScrollBar,)):
            continue
        # 未参与布局的控件（出生几何）几何无意义，越界判定会全是误报
        if (w.width() == 640 and w.height() == 480) or w.height() == 480 and w.width() <= 110:
            continue
        pw = w.parentWidget()
        if pw is None or pw is root:
            continue
        if pw.height() == 480 and pw.width() <= 640:
            continue
        if isinstance(pw, (QAbstractItemView, QComboBox)):
            continue
        rw = rect_in(w, pw)
        if not QRect(0, 0, pw.width(), pw.height()).contains(rw):
            clipped.append((w, rw, pw.size()))

    print(f"\n=== {name} ===")
    if not issues:
        print("  无控件互相遮挡")
    for a, b, ra, rb, inter in issues[:14]:
        print(f"  !! {type(a).__name__}('{(a.text()[:14] if hasattr(a,'text') else '')}') "
              f"{ra.getRect()} ∩ {type(b).__name__}('{(b.text()[:14] if hasattr(b,'text') else '')}') "
              f"{rb.getRect()}  → 重叠 {inter.getRect()}")
    if clipped:
        print("  超出父控件：")
        for w, rw, psz in clipped[:14]:
            print(f"     {type(w).__name__}('{(w.text()[:12] if hasattr(w,'text') else '')}') "
                  f"{rw.getRect()} 超出父 {psz.width()}x{psz.height()}")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from app import theme
    from app.app_data import ClassManager
    from app.ui_main import MainWindow
    from app.ui_dialogs import (RosterEditorDialog, AppSettingsDialog, ClassNameDialog,
                                StudentPickDialog, AdminPasswordDialog)

    theme.register_fonts(str(ROOT))
    theme.apply_theme(app)
    from tools.probes._probe_env import temp_classes
    base = temp_classes("rp_audit_")
    win = MainWindow(ClassManager(str(base)))
    win.startup()
    win.resize(1400, 860)
    win.show()
    app.processEvents()

    page = win.draw_page
    page.num_label.set_now("08")
    page._set_state("result")
    page._set_name("陈泽恩")
    page._refresh_hint()
    app.processEvents()
    audit(win.draw_page, "抽号页（结果态）")

    import time
    for i, nm in ((1, "抽号记录页"), (2, "概率统计页"), (3, "配置展示页"), (4, "屏蔽管理页")):
        win.stack.setCurrentIndex(i)
        t = time.time()
        while time.time() - t < 0.35:          # 让布局/动画跑完再量
            app.processEvents()
            time.sleep(0.01)
        cur = win.stack.currentWidget()
        lay = cur.layout()
        if lay is not None:
            lay.activate()
        app.processEvents()
        audit(cur, nm)

    win.stack.setCurrentIndex(0)
    app.processEvents()

    dlg = RosterEditorDialog(win, win.store)
    dlg.show(); app.processEvents()
    audit(dlg.card, "名单编辑弹窗")
    dlg.close()

    dlg = AppSettingsDialog(win, win.store, win.cfg)
    dlg.show(); app.processEvents()
    audit(dlg.card, "设置弹窗")
    dlg.close()

    dlg = ClassNameDialog(win, "新建班级", "", "请输入新班级名称：")
    dlg.show(); app.processEvents()
    audit(dlg.card, "班级命名弹窗")
    dlg.close()

    win.close()


if __name__ == "__main__":
    main()
