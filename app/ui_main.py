# -*- coding: utf-8 -*-
"""
主窗口：顶栏（标题 + 班级切换 + 班级管理 + 模式徽章 + 设置）、
Material 3 底部导航（动画指示器）、背景有机色块、快捷键系统：
- 空格 = 开始 / 停止抽号（QShortcut 全局，不受焦点按钮影响）
- R = 重置本轮　E = 导出记录　ESC = 关闭弹窗　← / → = 切换班级
「设置」打开应用内设置弹窗（语言 / 引导模式 / 防重；即时生效）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QComboBox, QLabel, QLineEdit, QSpinBox, QStackedWidget)

from . import app_data
from .app_data import ClassManager, ClassStore, MODE_ADVANCED
from .theme import COLORS, serif_style, paper_texture
from .lang import t, set_lang, get_lang
from .ui_widgets import (make_button, ask, inform, Badge, fade_slide_in, fade_in,
                         NavBar, snack)
from .ui_pages import DrawPage, HistoryPage, StatsPage, ConfigPage, ShieldPage
from .ui_dialogs import ClassNameDialog, SetupWizard, AppSettingsDialog


class BgCanvas(QWidget):
    """
    有机背景画布：米白底色 + 低透明莫兰迪色块（倾斜椭圆 / 圆角方块）
    + 全局纸纹噪点 + 顶栏下方的手绘波浪线。全部极其克制（低透明度）。
    """

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        w, h = float(r.width()), float(r.height())

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["cream"]))
        p.drawRect(r)

        def blob(cx, cy, bw, bh, rot, color, alpha):
            p.save()
            p.translate(cx, cy)
            p.rotate(rot)
            c = QColor(color)
            c.setAlpha(alpha)
            p.setBrush(c)
            p.drawEllipse(QRectF(-bw / 2, -bh / 2, bw, bh))
            p.restore()

        blob(w * 0.86, h * 0.10, 540, 360, -10, COLORS["blue_soft"], 64)
        blob(w * 0.05, h * 0.46, 420, 300, 16, COLORS["green_soft"], 55)
        p.save()
        p.translate(w * 0.93, h * 0.62)
        p.rotate(14)
        c = QColor(COLORS["camel_soft"])
        c.setAlpha(58)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(-110, -150, 220, 300), 30, 30)
        p.restore()
        blob(w * 0.10, h * 0.90, 190, 150, -6, "#EFDFDD", 70)

        # 手绘波浪线（标题下方；驼色）
        p.save()
        pen = QPen(QColor(COLORS["camel"]), 1.8, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        path = QPainterPath()
        x0, y0, amp = 26.0, 62.0, 4.5
        path.moveTo(x0, y0)
        step = 12.0
        for k in range(11):
            path.quadTo(x0 + step * (k + 0.5), y0 + (amp if k % 2 == 0 else -amp),
                        x0 + step * (k + 1), y0)
        p.drawPath(path)
        p.restore()

        # 全局纸纹噪点（低存在感）
        p.setOpacity(0.5)
        p.drawTiledPixmap(r, paper_texture())
        p.setOpacity(1.0)
        p.end()


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self, manager: ClassManager):
        super().__init__()
        self.manager = manager
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self.setWindowTitle(t("app_title"))
        self._build()
        self._bind()

    # ------------------------------------------------------------------ UI
    def _build(self):
        central = BgCanvas()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 顶栏 ----------
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(70)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(24, 8, 14, 6)
        tb.setSpacing(10)

        titlebox = QVBoxLayout()
        titlebox.setSpacing(0)
        self.title_lab = QLabel(t("app_title"))
        self.title_lab.setObjectName("AppTitle")
        titlebox.addWidget(self.title_lab)
        # 注解行：拉丁字距排（两种语言一致，不作为语言翻译项）
        self.caption_lab = QLabel("L U C K Y   D R A W")
        self.caption_lab.setObjectName("AppCaption")
        titlebox.addWidget(self.caption_lab)
        tb.addLayout(titlebox)

        tb.addSpacing(14)

        self.class_combo = QComboBox()
        self.class_combo.setMinimumWidth(190)
        self.class_combo.setMinimumHeight(44)
        self.class_combo.setToolTip(t("btn_settings"))
        tb.addWidget(self.class_combo)

        self.btn_new = make_button(t("btn_new_class"), "ghost", min_height=44)
        self.btn_rename = make_button(t("btn_rename_class"), "ghost", min_height=44)
        self.btn_delete = make_button(t("btn_delete_class"), "ghost", min_height=44)
        tb.addWidget(self.btn_new)
        tb.addWidget(self.btn_rename)
        tb.addWidget(self.btn_delete)

        tb.addStretch(1)

        self.mode_badge = QLabel()
        self.mode_badge.setObjectName("ModeBadge")
        tb.addWidget(self.mode_badge)

        self.btn_setup = make_button(t("btn_settings"), "ghost", min_height=44)
        self.btn_setup.setToolTip(t("btn_settings"))
        tb.addWidget(self.btn_setup)

        root.addWidget(topbar)

        # ---------- 页面栈 + M3 底部导航 ----------
        self.stack = QStackedWidget()
        self.draw_page = DrawPage()
        self.history_page = HistoryPage()
        self.stats_page = StatsPage()
        self.config_page = ConfigPage()
        self.shield_page = ShieldPage()
        for pg in (self.draw_page, self.history_page, self.stats_page,
                   self.config_page, self.shield_page):
            self.stack.addWidget(pg)
        root.addWidget(self.stack, 1)

        self.nav = NavBar([
            t("nav_draw"), t("nav_history"), t("nav_stats"),
            t("nav_config"), t("nav_shield"),
        ])
        root.addWidget(self.nav)

        # 快捷键：QShortcut 在按键分发给焦点控件之前处理（不受按钮焦点影响）
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.setAutoRepeat(False)
        self.shortcut_space.setContext(Qt.WindowShortcut)
        self.shortcut_space.activated.connect(self._shortcut_toggle)
        self.shortcut_r = QShortcut(QKeySequence("R"), self)
        self.shortcut_r.setContext(Qt.WindowShortcut)
        self.shortcut_r.activated.connect(self._shortcut_reset)
        self.shortcut_e = QShortcut(QKeySequence("E"), self)
        self.shortcut_e.setContext(Qt.WindowShortcut)
        self.shortcut_e.activated.connect(self._shortcut_export)

    def _bind(self):
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)
        self.btn_new.clicked.connect(self._create_class)
        self.btn_rename.clicked.connect(self._rename_class)
        self.btn_delete.clicked.connect(self._delete_class)
        self.btn_setup.clicked.connect(self._open_settings)
        self.nav.changed.connect(self._on_nav_changed)
        self.config_page.on_reconfigure = self._reconfigure
        self.config_page.settings_changed.connect(self._on_settings_changed)

    # ------------------------------------------------------------- 快捷键
    def _shortcut_toggle(self):
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page.toggle()

    def _shortcut_reset(self):
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page._reset_round()

    def _shortcut_export(self):
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page._export()

    # ------------------------------------------------------------- 启动
    def startup(self):
        """启动流程（按 6.8）：目录/模板/默认班级 → 备份恢复 → 引导向导。"""
        self.manager.ensure_dirs()
        self.manager.ensure_template()
        first = self.manager.ensure_default_class()

        last = self._load_last_class()
        name = last if last in self.manager.list_classes() else first

        self._reload_class(name, allow_wizard=True)

    def _load_last_class(self) -> str:
        try:
            p = self.manager.base / "last_class.txt"
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return ""

    def _save_last_class(self, name: str):
        try:
            (self.manager.base / "last_class.txt").write_text(name, encoding="utf-8")
        except Exception:
            pass

    # ---------------------------------------------------- 班级加载与切换
    def _reload_class(self, name: str, allow_wizard: bool = True) -> bool:
        if name not in self.manager.list_classes():
            names = self.manager.list_classes()
            name = names[0] if names else self.manager.create_class("默认班级")
        self.store = self.manager.get_class(name)
        self.cfg = self.store.load_config()

        app_data.daily_maintenance(self.store)
        app_data.repair_history(self.store)

        if self.store.needs_setup:
            if not self._run_wizard(t("confirm_break_fmt", name=name)):
                return False
        elif int(self.cfg.get("total_count", 0)) <= 0:
            if allow_wizard and not self._run_wizard():
                return False
        else:
            self.store.backup_config(self.cfg)

        self._save_last_class(name)
        self._sync_combo(name)
        self._refresh_all()
        return True

    def _sync_combo(self, current: str):
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        for n in self.manager.list_classes():
            self.class_combo.addItem(n)
        idx = self.class_combo.findText(current)
        if idx >= 0:
            self.class_combo.setCurrentIndex(idx)
        self.class_combo.blockSignals(False)

    def _refresh_all(self):
        if not self.store:
            return
        mode = self.cfg.get("mode", app_data.MODE_SIMPLE)
        self.mode_badge.setText(t("badge_advanced") if mode == MODE_ADVANCED
                                else t("badge_simple"))
        self.draw_page.set_store(self.store, self.cfg)
        self.history_page.set_store(self.store)
        self.stats_page.set_store(self.store)
        self.config_page.set_store(self.store, self.cfg)
        self.shield_page.set_store(self.store, self.cfg)

    def _on_settings_changed(self):
        """防重等设置变更后的联动：重新读取配置并刷新摇号池等页面（不播入场动画）。"""
        if not self.store:
            return
        self.cfg = self.store.load_config()
        mode = self.cfg.get("mode", app_data.MODE_SIMPLE)
        self.mode_badge.setText(t("badge_advanced") if mode == MODE_ADVANCED
                                else t("badge_simple"))
        self.draw_page.cfg = self.cfg
        self.draw_page.refresh()
        self.history_page.refresh()
        self.stats_page.refresh()
        self.shield_page.refresh()
        self.config_page.cfg = self.cfg
        self.config_page.refresh()

    def _refresh_page(self, index: int):
        pages = [self.draw_page, self.history_page, self.stats_page,
                 self.config_page, self.shield_page]
        if 0 <= index < len(pages):
            pages[index].refresh()

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        self._refresh_page(index)
        pages = [self.draw_page, self.history_page, self.stats_page,
                 self.config_page, self.shield_page]
        if 0 <= index < len(pages) and self.isVisible():
            fade_in(pages[index], dur=260, delay=30)

    # ------------------------------------------------------ 班级管理操作
    def _create_class(self):
        dlg = ClassNameDialog(self, t("dlg_title_new"), "", t("info_classname_hint"))
        if not dlg.exec():
            return
        new_name = self.manager.create_class(dlg.name)
        self._reload_class(new_name)
        snack(self, t("info_created_fmt", name=new_name))

    def _rename_class(self):
        if not self.store:
            return
        dlg = ClassNameDialog(self, t("dlg_title_rename"), self.store.name,
                              t("info_rename_hint"))
        if not dlg.exec():
            return
        new = dlg.name
        if new == self.store.name:
            return
        try:
            self.manager.rename_class(self.store.name, new)
        except FileExistsError:
            inform(self, t("dlg_title_rename"), t("err_name_exists_fmt", name=new), warn=True)
            return
        self._reload_class(new)

    def _delete_class(self):
        if not self.store:
            return
        name = self.store.name
        if not ask(self, t("dlg_title_new"),
                   t("confirm_delete_class_fmt", name=name),
                   yes=t("dlg_delete")):
            return
        if not ask(self, t("dlg_title_new"),
                   t("confirm_delete_class2_fmt", name=name),
                   yes=t("dlg_still"), no=t("dlg_back")):
            return
        self.manager.delete_class(name)
        names = self.manager.list_classes()
        if not names:
            self.manager.create_class("默认班级")
            names = self.manager.list_classes()
        self._reload_class(names[0])

    # ------------------------------------------------------ 设置 / 向导
    def _open_settings(self):
        """应用内设置弹窗：语言 / 引导模式入口 / 防重。"""
        dlg = AppSettingsDialog(self, self.store, self.cfg)
        if dlg.exec() and dlg.applied:
            self._on_settings_changed()
            self.apply_lang()
            snack(self, t("settings_saved"))

    def _reconfigure(self):
        if not self.store:
            return
        if self._run_wizard():
            self._on_settings_changed()
            snack(self, t("info_config_done", name=self.store.name))

    def _run_wizard(self, reason: str = "") -> bool:
        dlg = SetupWizard(self, self.store, self.cfg if not self.store.needs_setup else None)
        if reason:
            dlg.setWindowTitle(t("wizard_title_broken_fmt", name=self.store.name))
        if dlg.exec():
            self.cfg = self.store.load_config()
            return True
        return False

    # ------------------------------------------------------ 语言切换
    def apply_lang(self, code: str | None = None):
        """应用界面语言（即时生效）：顶栏 / 导航 / 各页面文案。"""
        if code:
            set_lang(code)
        self.setWindowTitle(t("app_title"))
        self.title_lab.setText(t("app_title"))
        self.caption_lab.setText("L U C K Y   D R A W")   # 注解行不随语言翻译
        self.btn_new.setText(t("btn_new_class"))
        self.btn_rename.setText(t("btn_rename_class"))
        self.btn_delete.setText(t("btn_delete_class"))
        self.btn_setup.setText(t("btn_settings"))
        self.nav.setLabels([t("nav_draw"), t("nav_history"), t("nav_stats"),
                            t("nav_config"), t("nav_shield")])
        for pg in (self.draw_page, self.history_page, self.stats_page,
                   self.config_page, self.shield_page):
            getattr(pg, "retranslate", lambda: None)()
        self._refresh_all()
        # 避免重播入场动画：直接刷新数据
        self.draw_page.refresh()

    # ------------------------------------------------------------- 快捷键（方向键）
    def keyPressEvent(self, event):
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QSpinBox)):
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Left:
            self._step_class(-1)
            return
        elif key == Qt.Key_Right:
            self._step_class(1)
            return
        super().keyPressEvent(event)

    def _step_class(self, delta):
        names = self.manager.list_classes()
        if not names or not self.store:
            return
        try:
            idx = names.index(self.store.name)
        except ValueError:
            idx = 0
        idx = (idx + delta) % len(names)
        if names[idx] != self.store.name:
            self._reload_class(names[idx])
            self.nav.setCurrentIndex(0)

    def _on_class_changed(self, idx: int):
        if idx < 0:
            return
        name = self.class_combo.itemText(idx)
        if self.store and name == self.store.name:
            return
        self._reload_class(name)

    # -------------------------------------------------------------- 动画
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_entrance_done", False):
            self._entrance_done = True
            topbar = self.centralWidget().findChild(QWidget, "TopBar")
            if topbar:
                fade_slide_in(topbar, dx=0, dy=-14, dur=420, delay=150)
            fade_slide_in(self.nav, dx=0, dy=18, dur=460, delay=320)

    # -------------------------------------------------------------- 关闭
    def closeEvent(self, event):
        self.draw_page.stop_silent()   # 所有数据已在抽号时即时落盘
        super().closeEvent(event)
