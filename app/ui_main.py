# -*- coding: utf-8 -*-
"""
主窗口：M3 顶栏（标题 + 班级切换 + 班级管理 + 模式徽章 + 设置）、
底部导航（动画指示器）、快捷键：
- 空格 = 开始 / 停止抽号
- B = 批量抽号　R = 重置本轮　E = 导出记录　ESC = 关闭弹窗　← / → = 切换班级
「设置」打开应用内设置弹窗（语言 / 引导模式 / 防重；即时生效）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QComboBox, QLabel, QLineEdit, QSpinBox, QStackedWidget, QMenu, QFrame)

from . import app_data
from .motion import page_enter as m_page_enter
from .app_data import ClassManager, ClassStore, MODE_ADVANCED
from .theme import COLORS
from .lang import t, set_lang
from .ui_widgets import (make_button, ask, inform, Badge,
                         NavBar, snack, enable_touch_view, hairline, IconButton, IconGlyph)
from .ui_pages import DrawPage, HistoryPage, StatsPage, ConfigPage, ShieldPage
from .ui_dialogs import ClassNameDialog, SetupWizard, AppSettingsDialog


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
        central = QWidget()
        central.setObjectName("RootSurface")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- M3 top app bar ----------
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(64)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(24, 0, 16, 0)
        tb.setSpacing(10)

        self.title_lab = QLabel(t("app_title"))
        self.title_lab.setObjectName("AppTitle")
        tb.addWidget(self.title_lab)
        self.caption_lab = QLabel("LUCKY DRAW")
        self.caption_lab.setStyleSheet(
            f"color:{COLORS['outline']}; font-size:9px; letter-spacing:3px;"
            "background:transparent;")
        tb.addSpacing(8)
        tb.addWidget(self.caption_lab, 0, Qt.AlignVCenter)
        tb.addSpacing(14)

        # 班级选择：M3 圆角容器 + 下拉 + 折叠箭头
        self.class_chip = QFrame()
        self.class_chip.setObjectName("ClassChip")
        self.class_chip.setFixedHeight(40)
        cc = QHBoxLayout(self.class_chip)
        cc.setContentsMargins(14, 0, 10, 0)
        cc.setSpacing(8)
        self.class_cap = QLabel(t("class_label"))
        self.class_cap.setStyleSheet(
            f"color:{COLORS['on_surface_variant']}; font-size:12px; background:transparent;")
        cc.addWidget(self.class_cap)
        self.class_combo = QComboBox()
        self.class_combo.setMinimumWidth(150)
        self.class_combo.setFixedHeight(36)
        self.class_combo.setFocusPolicy(Qt.NoFocus)
        self.class_combo.setObjectName("ClassCombo")
        cc.addWidget(self.class_combo)
        self.class_arrow = IconGlyph("chevron_down", 16, COLORS["on_surface_variant"])
        cc.addWidget(self.class_arrow)
        tb.addWidget(self.class_chip)

        # 班级管理：统一收进“更多”菜单（窄屏也不挤）
        self.btn_new = make_button(t("btn_new_class"), "text", min_height=40)
        self.btn_rename = make_button(t("btn_rename_class"), "text", min_height=40)
        self.btn_delete = make_button(t("btn_delete_class"), "text", min_height=40)
        for b in (self.btn_new, self.btn_rename, self.btn_delete):
            b.hide()

        self.btn_more = IconButton("more", self, 40, t("btn_class_menu"))
        self.menu_more = QMenu(self)
        self.menu_more.addAction(t("btn_new_class"), self._create_class)
        self.menu_more.addAction(t("btn_rename_class"), self._rename_class)
        self.menu_more.addAction(t("btn_delete_class"), self._delete_class)
        self.btn_more.clicked.connect(
            lambda: self.menu_more.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomRight())))
        tb.addWidget(self.btn_more)

        tb.addStretch(1)

        self.mode_badge = QLabel()
        self.mode_badge.setObjectName("ModeBadge")
        tb.addWidget(self.mode_badge)

        self.btn_setup = IconButton("tune", self, 44, t("btn_settings"))
        tb.addWidget(self.btn_setup)

        root.addWidget(topbar)

        # ---------- 页面栈 + 底部导航 ----------
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

        # 快捷键
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.setAutoRepeat(False)
        self.shortcut_space.setContext(Qt.WindowShortcut)
        self.shortcut_space.activated.connect(self._shortcut_toggle)
        for key, slot in (("R", self._shortcut_reset), ("E", self._shortcut_export),
                          ("B", self._shortcut_batch)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(slot)
            setattr(self, f"shortcut_{key.lower()}", sc)

    def _bind(self):
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)
        self.btn_new.clicked.connect(self._create_class)
        self.btn_rename.clicked.connect(self._rename_class)
        self.btn_delete.clicked.connect(self._delete_class)
        self.btn_setup.clicked.connect(self._open_settings)
        self.nav.changed.connect(self._on_nav_changed)
        self.config_page.on_reconfigure = self._reconfigure
        self.config_page.settings_changed.connect(self._on_settings_changed)
        self.history_page.history_changed.connect(self._on_history_changed)
        try:
            enable_touch_view(self.class_combo.view())
        except Exception:
            pass

    # ------------------------------------------------------------- 快捷键
    def _typing(self) -> bool:
        f = self.focusWidget()
        return isinstance(f, (QLineEdit, QSpinBox))

    def _shortcut_toggle(self):
        if self._typing():
            return
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page.toggle()

    def _shortcut_reset(self):
        if self._typing():
            return
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page._reset_round()

    def _shortcut_export(self):
        if self._typing():
            return
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page._export()

    def _shortcut_batch(self):
        if self._typing():
            return
        if self.stack.currentWidget() is self.draw_page:
            self.draw_page.batch_draw()

    # ------------------------------------------------------------- 启动
    def startup(self):
        self.manager.ensure_dirs()
        self.manager.ensure_template()
        first = self.manager.ensure_default_class()
        last = self._load_last_class()
        # 只认带 config.json 的班级：classes/ 里混进的无配置目录（backups /
        # template 等）如果按名字排到最前，会让程序启动即弹「首次使用向导」。
        usable = self.manager.usable_classes() or self.manager.list_classes()
        if last in usable:
            name = last
        elif first in usable:
            name = first
        else:
            name = usable[0] if usable else first
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
        self.mode_badge.setText("· " + (t("badge_advanced") if mode == MODE_ADVANCED
                                        else t("badge_simple")))
        self.draw_page.set_store(self.store, self.cfg)
        self.history_page.set_store(self.store)
        self.stats_page.set_store(self.store)
        self.config_page.set_store(self.store, self.cfg)
        self.shield_page.set_store(self.store, self.cfg)

    def _on_settings_changed(self):
        if not self.store:
            return
        self.cfg = self.store.load_config()
        mode = self.cfg.get("mode", app_data.MODE_SIMPLE)
        self.mode_badge.setText("· " + (t("badge_advanced") if mode == MODE_ADVANCED
                                        else t("badge_simple")))
        self.draw_page.cfg = self.cfg
        self.draw_page.refresh()
        self.history_page.refresh()
        self.stats_page.refresh()
        self.shield_page.refresh()
        self.config_page.cfg = self.cfg
        self.config_page.refresh()

    def _on_history_changed(self):
        """记录被删除后：统计、配置、抽号页同步刷新（历史是统计的数据源）。"""
        if not self.store:
            return
        self.stats_page.refresh()
        self.config_page.refresh()
        self.draw_page.refresh()

    def _refresh_page(self, index: int):
        pages = [self.draw_page, self.history_page, self.stats_page,
                 self.config_page, self.shield_page]
        if 0 <= index < len(pages):
            pages[index].refresh()

    def _on_nav_changed(self, index: int):
        # 顺序很重要：先刷新目标页内容，再切换，最后才动效。
        # 先切后刷新会让页面带着旧内容画出一帧再跳变。
        self._refresh_page(index)
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        if self.isVisible() and page is not None:
            # 整页只做一个动作：上浮 8px + 淡入 200ms，零延迟、不缩放。
            # 旧实现是「三张卡片各差 80ms 缩到 0.975 再飘进来」——大块错落
            # 像 PPT 逐条出现，而且 delay=80 会先以全亮渲染一帧再突然消失，
            # 看上去就是一闪 + 糊上来；缩放还会让大数字在移动中重采样发虚。
            m_page_enter(page)
        # 导航栏图标微缩放脉冲
        try:
            self.nav._pulse_icon(index)
        except Exception:
            pass

    # ------------------------------------------------------ 班级管理
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
                   t("confirm_delete_class_fmt", name=name), yes=t("dlg_delete")):
            return
        if not ask(self, t("dlg_title_new"),
                   t("confirm_delete_class2_fmt", name=name),
                   yes=t("dlg_still"), no=t("dlg_back")):
            return
        try:
            self.manager.delete_class(name)
        except OSError as e:
            inform(self, t("dlg_delete"), str(e), warn=True)
            return
        names = self.manager.list_classes()
        if not names:
            self.manager.create_class("默认班级")
            names = self.manager.list_classes()
        self._reload_class(names[0])

    # ------------------------------------------------------ 设置 / 向导
    def _open_settings(self):
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

    # ------------------------------------------------------ 语言
    def apply_lang(self, code: str | None = None):
        if code:
            set_lang(code)
        self.setWindowTitle(t("app_title"))
        self.title_lab.setText(t("app_title"))
        self.btn_new.setText(t("btn_new_class"))
        self.btn_rename.setText(t("btn_rename_class"))
        self.btn_delete.setText(t("btn_delete_class"))
        self.btn_setup.setToolTip(t("btn_settings"))
        self.class_cap.setText(t("class_label"))
        acts = self.menu_more.actions()
        for act, key in zip(acts, ("btn_new_class", "btn_rename_class", "btn_delete_class")):
            act.setText(t(key))
        self.nav.setLabels([t("nav_draw"), t("nav_history"), t("nav_stats"),
                            t("nav_config"), t("nav_shield")])
        for pg in (self.draw_page, self.history_page, self.stats_page,
                   self.config_page, self.shield_page):
            getattr(pg, "retranslate", lambda: None)()
        self._refresh_all()
        self.draw_page.refresh()

    # ------------------------------------------------------------- 键盘
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
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._responsive()

    def _update_scale(self):
        dp = self.draw_page
        if hasattr(dp, '_apply_num_size') and dp.num_label.text():
            dp._apply_num_size(len(dp.num_label.text()))
        # 内容跟随缩放
        dp = self.draw_page
        if hasattr(dp, '_stretch_grid'):
            dp._stretch_grid()
        if hasattr(dp, '_scale_empty_state'):
            dp._scale_empty_state()
        if hasattr(dp, '_apply_num_size') and dp.num_label.text():
            dp._apply_num_size(len(dp.num_label.text()))

    def _responsive(self):
        """窄屏折叠：任何缩放下顶栏都不互相挤压。"""
        w = self.width()
        self.class_cap.setVisible(w >= 820)
        self.class_chip.setMinimumWidth(150 if w < 820 else 210)
        self.mode_badge.setVisible(w >= 700)

    def showEvent(self, event):
        super().showEvent(event)
        self._responsive()
        if not getattr(self, "_entrance_done", False):
            self._entrance_done = True
            # 启动入场：内容区整体上浮一次即可（顶栏/导航属外壳，瞬时出现
            # 更自然）。showEvent 在首帧绘制之前，零延迟不会产生「先亮后暗」。
            m_page_enter(self.draw_page, dur=300, dy=12)

    def closeEvent(self, event):
        self.draw_page.stop_silent()
        app_data.flush()          # 关闭前把后台写盘队列清空，保证不丢最后一笔记录
        super().closeEvent(event)
