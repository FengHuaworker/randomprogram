# -*- coding: utf-8 -*-
"""
弹窗层（全部为应用内自绘弹窗，无系统弹窗）：
- ClassNameDialog：班级名输入；
- SetupWizard：双模式配置引导向导（简易/高级）；
- RosterEditorDialog：名单编辑器；
- StudentPickDialog：屏蔽学生多选；
- 名单上传 / 重新上传：AppFilePickerDialog（应用内文件选择器）。
均支持：ESC 关闭、点遮罩关闭、触摸操作（触控目标 >= 44px、触屏滚动）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QDateTime, QTime, QPropertyAnimation, QPoint, QSize
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QListWidget, QListWidgetItem, QStackedWidget, QWidget,
                               QFrame, QAbstractItemView, QHeaderView, QRadioButton,
                               QDateTimeEdit)

from . import app_data
from .app_data import ClassStore, MODE_SIMPLE, MODE_ADVANCED, ANTI_DUP_DEFAULT_HOURS
from .lang import t, set_lang, get_lang
from .theme import COLORS, serif_style, standard
from .ui_widgets import (make_button, ask, inform, MaterialDialog,
                         AppFilePickerDialog, enable_touch_scroll, SwitchControl,
                         ChoiceChip, SegmentedControl,
                         cross_fade, swap_text, swap_stack_page, pulse_opacity,
                         reveal_widget, fade_in, stagger_fade_in)
from .motion import (pop_in as m_pop_in, bounce as m_bounce,
                     stagger as m_stagger, flip_text as m_flip,
                     slide_switch as m_switch, burst as m_burst,
                     animate as m_animate, shake as m_shake)


class ClassNameDialog(MaterialDialog):
    """输入班级名称（新建/重命名共用）。"""

    def __init__(self, parent, title: str, initial: str = "", hint: str = ""):
        super().__init__(parent, title, card_width=380, scrim_cancel=True)
        lab = QLabel(hint or "请输入班级名称", self.body)
        lab.setStyleSheet(f"font-size:14px; color:{COLORS['ink']}; background:transparent;")
        self.body_lay.addWidget(lab)
        self.edit = QLineEdit(initial, self.body)
        self.edit.setPlaceholderText(t("classname_placeholder"))
        self.edit.setMaxLength(30)
        self.body_lay.addWidget(self.edit)
        self.add_action("取消", role="reject", primary=False)
        ok = self.add_action("确定", role="none", primary=True)
        ok.clicked.connect(self._on_ok)
        self.edit.returnPressed.connect(self._on_ok)
        self.name = ""
        QTimer.singleShot(260, self.edit.setFocus)

    def _on_ok(self):
        name = app_data.safe_name(self.edit.text())
        if not name or (name == "未命名班级" and not self.edit.text().strip()):
            self.edit.setFocus()
            m_bounce(self.edit, s=0.93, dur=380)   # 弹性回弹代替无反馈
            return
        self.name = name
        self.accept()


class _OptionCard(QFrame):
    """向导里的模式选择卡（简易 / 高级），点击切换选中态（触控友好）。
    on_clicked：可选回调（用于实现多卡互斥），回调参数 = 当前是否即将选中。"""

    def __init__(self, title: str, desc: str, selected: bool = False):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(92)
        self.setProperty("optCard", True)
        self._selected = bool(selected)
        self.on_clicked = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(6)
        self.t_lab = QLabel(title)
        self.t_lab.setStyleSheet(
            serif_style(17, COLORS["ink"], 600) + "; background:transparent;")
        self.d_lab = QLabel(desc)
        self.d_lab.setWordWrap(True)
        self.d_lab.setStyleSheet(f"font-size:12.5px; color:{COLORS['ink_soft']}; background:transparent;")
        lay.addWidget(self.t_lab)
        lay.addWidget(self.d_lab)
        self._apply_style()
        self.mousePressEvent = self._click

    def _click(self, ev):
        if self.on_clicked is not None:
            self.on_clicked(not self._selected)   # 业务层决定互斥
        else:
            self.set_selected(not self._selected)

    def set_selected(self, sel: bool):
        changed = self._selected != bool(sel)
        self._selected = bool(sel)
        self._apply_style()
        if changed:
            m_bounce(self, s=1.05, dur=440)  # 整张卡弹性回弹，选中更有反馈

    def is_checked(self) -> bool:
        return self._selected

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(
                f'QFrame[optCard="true"] {{ background:{COLORS["secondary_container"]};'
                f' border:2px solid {COLORS["primary"]}; border-radius:16px; }}')
        else:
            self.setStyleSheet(
                f'QFrame[optCard="true"] {{ background:{COLORS["surface_container_lowest"]};'
                f' border:1px solid {COLORS["outline_variant"]}; border-radius:16px; }}'
                f'QFrame[optCard="true"]:hover {{ background:{COLORS["surface_container_low"]}; }}')


class SetupWizard(MaterialDialog):
    """
    双模式配置引导向导：
    第 1 步：选择简易 / 高级；第 2 步（简易）：输入人数；
    第 2~3 步（高级）：人数 -> 上传名单（应用内文件选择器 + 模板下载）。
    完成后直接写入该班级配置（含人数、名单），重启自动加载。
    """

    def __init__(self, parent, store: ClassStore, existing_cfg: dict | None = None):
        self.store = store
        self.cfg = dict(existing_cfg) if existing_cfg else store.load_config()
        super().__init__(parent, t("wizard_title_fmt", name=store.name), card_width=560, scrim_cancel=True)
        self._roster: list[str] = []

        self.step_label = QLabel("", self.body)
        self.step_label.setAlignment(Qt.AlignCenter)
        self.step_label.setStyleSheet(f"font-size:12.5px; color:{COLORS['ink_soft']}; background:transparent;")
        self.body_lay.addWidget(self.step_label)

        self.stack = QStackedWidget(self.body)
        self.stack.setMinimumHeight(270)
        self.body_lay.addWidget(self.stack, 1)

        # ---------- 页面 0：选择模式 ----------
        p0 = QWidget()
        v0 = QVBoxLayout(p0)
        v0.setContentsMargins(8, 8, 8, 8)
        v0.setSpacing(12)
        self.card_simple = _OptionCard(t("mode_simple"), t("mode_simple_desc"))
        self.card_advanced = _OptionCard(t("mode_advanced"), t("mode_advanced_desc"))
        # 互斥：同时只能选中一种模式
        self.card_simple.on_clicked = lambda sel: self._select_mode("simple", sel)
        self.card_advanced.on_clicked = lambda sel: self._select_mode("advanced", sel)
        v0.addWidget(self.card_simple)
        v0.addWidget(self.card_advanced)
        p0.setLayout(v0)
        self.stack.addWidget(p0)

        # ---------- 页面 1：简易模式人数 ----------
        p1 = QWidget()
        v1 = QVBoxLayout(p1)
        v1.setContentsMargins(8, 8, 8, 8)
        v1.setSpacing(12)
        v1.addWidget(QLabel(t("wiz_total")))
        self.simple_count = QSpinBox()
        self.simple_count.setRange(1, 999)
        self.simple_count.setValue(max(1, int(self.cfg.get("total_count", 0)) or 1))
        self.simple_count.setSuffix(" 人")
        self.simple_count.setMinimumHeight(48)
        v1.addWidget(self.simple_count)
        v1.addStretch(1)
        p1.setLayout(v1)
        self.stack.addWidget(p1)

        # ---------- 页面 2：高级模式人数 ----------
        p2 = QWidget()
        v2 = QVBoxLayout(p2)
        v2.setContentsMargins(8, 8, 8, 8)
        v2.setSpacing(12)
        v2.addWidget(QLabel(t("wiz_total_adv")))
        self.adv_count = QSpinBox()
        self.adv_count.setRange(1, 999)
        self.adv_count.setValue(max(1, int(self.cfg.get("total_count", 0)) or 1))
        self.adv_count.setSuffix(" 人")
        self.adv_count.setMinimumHeight(48)
        v2.addWidget(self.adv_count)
        v2.addStretch(1)
        p2.setLayout(v2)
        self.stack.addWidget(p2)

        # ---------- 页面 3：高级模式上传名单 ----------
        p3 = QWidget()
        v3 = QVBoxLayout(p3)
        v3.setContentsMargins(8, 8, 8, 8)
        v3.setSpacing(10)
        tip = QLabel(t("wiz_roster_tip"))
        tip.setWordWrap(True)
        tip.setStyleSheet(f"font-size:12px; color:{COLORS['ink_soft']}; background:transparent;")
        v3.addWidget(tip)
        row = QHBoxLayout()
        self.btn_pick = make_button(t("wiz_pick_file") + "(.txt)", "primary", min_height=48)
        self.btn_tpl = make_button(t("wiz_download_tpl"), "ghost", min_height=44)
        row.addWidget(self.btn_pick, 1)
        row.addWidget(self.btn_tpl)
        v3.addLayout(row)
        self.roster_info = QLabel(t("wiz_roster_none"))
        self.roster_info.setWordWrap(True)
        self.roster_info.setStyleSheet(f"font-size:13px; color:{COLORS['green_dark']}; background:transparent;")
        v3.addWidget(self.roster_info)
        self.roster_prev = QLabel("")
        # 预览改成「一行顿号分隔」：宋体的 lineSpacing 正好等于字号，多行中文
        # 会一行压一行（看着像姓名互相遮挡）。单段文字自动换行就不会有行距问题。
        self.roster_prev.setWordWrap(True)
        self.roster_prev.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.roster_prev.setMinimumHeight(62)
        self.roster_prev.setMaximumHeight(92)
        self.roster_prev.setStyleSheet(
            f"font-size:12.5px; color:{COLORS['ink_soft']}; background:{COLORS['paper_deep']};"
            "border-radius:8px; padding:8px 10px;")
        v3.addWidget(self.roster_prev)
        v3.addStretch(1)
        p3.setLayout(v3)
        self.stack.addWidget(p3)

        # ---------- 操作 ----------
        self.btn_back = self.add_action(t("wiz_prev"), role="none", primary=False)
        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        self.btn_next = self.add_action(t("wiz_next"), role="none", primary=True)
        self.btn_back.clicked.connect(self._back)
        self.btn_next.clicked.connect(self._next)
        self.btn_pick.clicked.connect(self._pick_roster)
        self.btn_tpl.clicked.connect(self._download_template)

        self._state = "mode"
        self._refresh()

    def _select_mode(self, which: str, sel: bool):
        """互斥选择：选中的卡高亮，另一张强制取消。"""
        if sel:
            self.card_simple.set_selected(which == "simple")
            self.card_advanced.set_selected(which == "advanced")
        else:
            # 允许点击已选中卡“取消选择”（但保证状态一致）
            if which == "simple":
                self.card_simple.set_selected(False)
            else:
                self.card_advanced.set_selected(False)
        self._refresh()

    # ---------- 状态机 ----------
    def _refresh(self):
        """步骤切换：淡出 → 换页/改文案 → 淡入（同页刷新不闪）。"""
        st = self._state
        if st == "mode":
            idx = 0
            step = t("wiz_step1")
            next_txt = t("wiz_next")
            back_on, next_on = False, True
        elif st == "count":
            is_adv = self.card_advanced.is_checked()
            idx = 2 if is_adv else 1
            step = t("wiz_step2", total=(3 if is_adv else 2))
            next_txt = t("wiz_next")
            back_on, next_on = True, True
        else:  # roster
            idx = 3
            step = t("wiz_step3")
            next_txt = t("wiz_done")
            back_on, next_on = True, bool(self._roster)

        def _apply_state():
            self.stack.setCurrentIndex(idx)   # on_mid 里切页，配合侧向滑动
            self.step_label.setText(step)
            self.btn_back.setEnabled(back_on)
            self.btn_next.setText(next_txt)
            self.btn_next.setEnabled(next_on)

        old_idx = self.stack.currentIndex()
        if old_idx != idx:
            m_switch(self.stack, _apply_state, forward=(idx > old_idx), dur=620)
        else:
            _apply_state()

    def _next(self):
        st = self._state
        if st == "mode":
            if not self.card_simple.is_checked() and not self.card_advanced.is_checked():
                inform(self, t("app_title"), t("wiz_pick_mode"))
                return
            self._state = "count"
        elif st == "count":
            if self.card_advanced.is_checked():
                self._state = "roster"
            else:
                self._apply()
                return
        elif st == "roster":
            self._apply()
            return
        self._refresh()

    def _back(self):
        if self._state == "count":
            self._state = "mode"
            self._refresh()
        elif self._state == "roster":
            self._state = "count"
            self._refresh()

    # ---------- 名单 ----------
    def _load_names_from(self, path: Path) -> list[str] | None:
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                raw = path.read_text(encoding="gbk")
            except Exception:
                inform(self, t("app_title"), t("wiz_read_fail"), warn=True)
                return None
        names = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not names:
            inform(self, t("app_title"), t("wiz_no_names"), warn=True)
            return None
        return names

    def _pick_roster(self):
        dlg = AppFilePickerDialog(self, "选择班级名单文件",
                                  start_dir=self.store.dir.parent.parent, suffixes=(".txt",))
        if dlg.exec():
            names = self._load_names_from(Path(dlg.selected_path))
            if names is None:
                return
            self._roster = names
            shown = "、".join(names[:10]) + ("……" if len(names) > 10 else "")
            m_flip(self.roster_info, t("wiz_roster_loaded", n=len(names)))
            self.roster_prev.setText(shown)
            m_pop_in(self.roster_prev, dy=16, s=0.94, dur=460)
            self._refresh()

    def _download_template(self):
        p = self.store.dir.parent.parent / "template" / "template.txt"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text(app_data.TEMPLATE_CONTENT, encoding="utf-8")
            inform(self, t("app_title"), t("wiz_tpl_done", path=p))
        except Exception:
            inform(self, t("app_title"), t("wiz_tpl_fail"), warn=True)

    # ---------- 完成：写入配置 ----------
    def _apply(self):
        cfg = self.store.load_config()
        is_adv = self.card_advanced.is_checked()
        if is_adv:
            cfg["mode"] = MODE_ADVANCED
            cfg["total_count"] = self.adv_count.value()
            if self._roster:
                cfg["total_count"] = len(self._roster)
                self.store.roster_write(self._roster)
        else:
            cfg["mode"] = MODE_SIMPLE
            cfg["total_count"] = self.simple_count.value()
        cfg.setdefault("anti_dup_enabled", True)
        cfg.setdefault("anti_dup_hours", ANTI_DUP_DEFAULT_HOURS)
        self.store.save_config(cfg)
        self.store.needs_setup = False
        self.accept()


class RosterEditorDialog(MaterialDialog):
    """
    名单编辑器：
    - 表格直接改姓名；追加 / 删除 / 上移 / 下移；学号 = 行号（自动顺延）；
    - “重新上传”= 应用内文件选择器覆盖导入；保存时自动同步总人数。
    """

    def __init__(self, parent, store: ClassStore):
        super().__init__(parent, t("roster_title_fmt", name=store.name), card_width=620, scrim_cancel=True)
        self.store = store
        self._names = store.roster_read()

        hint = QLabel(t("roster_edit_hint"), self.body)
        hint.setStyleSheet(f"font-size:12.5px; color:{COLORS['ink_soft']}; background:transparent;")
        self.body_lay.addWidget(hint)

        self.table = QTableWidget(0, 2, self.body)
        self.table.setHorizontalHeaderLabels([t("col_num"), t("col_name")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setMinimumHeight(290)
        enable_touch_scroll(self.table)
        self._fill()
        self.body_lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_add = make_button(t("roster_add"), "", min_height=44)
        self.btn_del = make_button(t("roster_del"), "danger", min_height=44)
        self.btn_up = make_button(t("roster_up"), "ghost", min_height=44)
        self.btn_down = make_button(t("roster_down"), "ghost", min_height=44)
        self.btn_reupload = make_button(t("roster_reupload"), "ghost", min_height=44)
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_del)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addStretch(1)
        row.addWidget(self.btn_reupload)
        self.body_lay.addLayout(row)

        self.count_label = QLabel(t("roster_count_fmt", n=len(self._names)), self.body)
        self.count_label.setStyleSheet(f"font-size:13px; color:{COLORS['ink_soft']}; background:transparent;")
        self.body_lay.addWidget(self.count_label)

        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        save = self.add_action(t("roster_save"), role="none", primary=True)
        save.clicked.connect(self._save)
        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._del)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_reupload.clicked.connect(self._reupload)

    def _fill(self):
        self.table.setRowCount(len(self._names))
        for i, n in enumerate(self._names):
            c0 = QTableWidgetItem(str(i + 1))
            c0.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(i, 0, c0)
            self.table.setItem(i, 1, QTableWidgetItem(n))
        # 重填后表格弹性淡入（构造时未显示会自动跳过，不会有多余动画）
        m_pop_in(self.table.viewport(), dy=14, s=0.975, dur=420)

    def _sync_count(self, with_fade: bool = True):
        m_flip(self.count_label, t("roster_count_fmt", n=self.table.rowCount()))
        if with_fade:
            m_pop_in(self.table.viewport(), dy=8, s=0.99, dur=340)

    def _collect(self) -> list[str]:
        names = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            name = (item.text().strip() if item else "").strip()
            if not name:
                name = f"学生{i + 1}"
            names.append(name)
        return names

    def _add(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        c0 = QTableWidgetItem(str(r + 1))
        c0.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(r, 0, c0)
        self.table.setItem(r, 1, QTableWidgetItem(f"学生{r + 1}"))
        self.table.setCurrentCell(r, 1)
        self.table.editItem(self.table.item(r, 1))
        self._sync_count(with_fade=False)   # 编辑态不做整表淡入，只让计数过渡

    def _del(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self.table.removeRow(r)
        self._renumber()
        self._sync_count()

    def _renumber(self):
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                item.setText(str(i + 1))

    def _move(self, delta: int):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        new = row + delta
        if new < 0 or new >= self.table.rowCount():
            return
        self._swap_rows(row, new)
        self.table.selectRow(new)
        m_pop_in(self.table.viewport(), dy=8, s=0.99, dur=340)  # 行交换弹性淡入

    def _swap_rows(self, a: int, b: int):
        c0, c1 = self.table.item(a, 0), self.table.item(a, 1)
        n0, n1 = self.table.item(b, 0), self.table.item(b, 1)
        self.table.setItem(a, 0, n0)
        self.table.setItem(a, 1, n1)
        self.table.setItem(b, 0, c0)
        self.table.setItem(b, 1, c1)
        self._renumber()

    def _reupload(self):
        dlg = AppFilePickerDialog(self, t("roster_reupload_title"), start_dir=self.store.dir.parent.parent,
                                  suffixes=(".txt",))
        if dlg.exec():
            path = Path(dlg.selected_path)
            try:
                raw = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                try:
                    raw = path.read_text(encoding="gbk")
                except Exception:
                    inform(self, "错误", "无法读取文件。", warn=True)
                    return
            names = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if not names:
                inform(self, "错误", "文件中没有有效姓名。", warn=True)
                return
            self._names = names
            self._fill()
            m_flip(self.count_label, t("roster_count_fmt", n=len(names)))

    def _save(self):
        names = self._collect()
        self.store.roster_write(names)
        cfg = self.store.load_config()
        cfg["total_count"] = len(names)
        self.store.save_config(cfg)
        self.accept()


class StudentPickDialog(MaterialDialog):
    """屏蔽管理用的学生多选对话框（选中项 = 要加入屏蔽的号码）。"""

    def __init__(self, parent, title: str, students: list[dict], preselected: set[int]):
        super().__init__(parent, title, card_width=440, scrim_cancel=True)
        self.students = students
        self._pre = set(preselected)

        self.search = QLineEdit(self.body)
        self.search.setPlaceholderText(t("pick_search"))
        self.search.setClearButtonEnabled(True)
        self.body_lay.addWidget(self.search)

        self.listw = QListWidget(self.body)
        self.listw.setSelectionMode(QAbstractItemView.NoSelection)
        self.listw.setMinimumHeight(320)
        enable_touch_scroll(self.listw)
        self.body_lay.addWidget(self.listw, 1)

        quick = QHBoxLayout()
        all_btn = make_button(t("pick_all"), "ghost", min_height=40)
        none_btn = make_button(t("pick_clear"), "ghost", min_height=40)
        quick.addWidget(all_btn)
        quick.addWidget(none_btn)
        quick.addStretch(1)
        self.body_lay.addLayout(quick)

        self.count_label = QLabel("", self.body)
        self.count_label.setStyleSheet(f"font-size:13px; color:{COLORS['ink_soft']}; background:transparent;")
        self.body_lay.addWidget(self.count_label)

        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        self.add_action(t("dlg_ok"), role="accept", primary=True)

        self.search.textChanged.connect(lambda t: self._fill(t))
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        self.listw.itemChanged.connect(lambda _: self._refresh_count())

        # 填充并刷新计数（count_label 已就绪；此前该顺序错误会导致构造抛异常）
        self._fill("")

    def _fill(self, needle: str):
        self.listw.clear()
        needle = needle.strip()
        for s in self.students:
            num, name = s["num"], s.get("name", "") or ""
            hay = f"{num} {name}"
            if needle and needle not in hay:
                continue
            item = QListWidgetItem(f"{num:02d}　{name if name else t('unnamed')}")
            item.setData(Qt.UserRole, num)
            item.setSizeHint(QSize(0, 46))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if num in self._pre else Qt.Unchecked)
            self.listw.addItem(item)
        self._refresh_count()
        # 搜索过滤是高频操作：动画自带重入保护，连打字不会反复闪
        m_pop_in(self.listw.viewport(), dy=10, s=0.985, dur=360)

    def _refresh_count(self):
        lbl = getattr(self, "count_label", None)
        if lbl is None:
            return
        m_flip(lbl, t("pick_count_fmt", n=len(self.selected())))

    def _set_all(self, state):
        # 逐项 setCheckState 会触发 N 次 itemChanged；先屏蔽，最后只刷新一次
        self.listw.blockSignals(True)
        for i in range(self.listw.count()):
            self.listw.item(i).setCheckState(state)
        self.listw.blockSignals(False)
        self._refresh_count()
        m_pop_in(self.listw.viewport(), dy=12, s=0.975, dur=420)

    def selected(self) -> set[int]:
        out = set()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if it.checkState() == Qt.Checked:
                out.add(int(it.data(Qt.UserRole)))
        return out


# ===========================================================================
# 设置弹窗：界面语言 / 引导模式入口 / 防重设置（应用内，即时生效）
# ===========================================================================

class AppSettingsDialog(MaterialDialog):
    """
    应用内设置：
    - 语言：中文 / English（切换后主窗口文案即时更新）；
    - 引导模式：可直接进入配置向导（模式 / 人数 / 名单）；
    - 防重设置：开关 + 时间窗口（与配置页联动）。
    保存后 applied=True，由主窗口做全局联动刷新。
    """

    def __init__(self, parent, store: ClassStore, cfg: dict):
        super().__init__(parent, t("settings_title"), card_width=540, scrim_cancel=True)
        self.store = store
        self.cfg = dict(cfg)
        self.applied = False

        # ---- 界面语言 ----
        lang_lab = QLabel(t("set_lang"), self.body)
        lang_lab.setStyleSheet(serif_style(16, COLORS["ink"], 600) + "; background:transparent;")
        self.body_lay.addWidget(lang_lab)
        self.seg_lang = SegmentedControl([t("lang_zh"), t("lang_en")],
                                         0 if get_lang() == "zh" else 1)
        self.body_lay.addWidget(self.seg_lang, 0, Qt.AlignLeft)

        # ---- 引导模式入口 ----
        mode_lab = QLabel(t("set_mode"), self.body)
        mode_lab.setStyleSheet(serif_style(16, COLORS["ink"], 600) + "; background:transparent;")
        self.body_lay.addWidget(mode_lab)
        self.btn_wizard = make_button(t("run_wizard"), "tonal", min_height=44)
        self.btn_wizard.clicked.connect(self._run_wizard)
        self.body_lay.addWidget(self.btn_wizard, 0, Qt.AlignLeft)

        # ---- 防重设置 ----
        anti_lab = QLabel(t("set_anti"), self.body)
        anti_lab.setStyleSheet(serif_style(16, COLORS["ink"], 600) + "; background:transparent;")
        self.body_lay.addWidget(anti_lab)
        # 说明文字单独占一整行：放在开关那一行里会被挤成三行，最后一行
        # 还会被行高裁掉一半（看着像「文字被控件压住」）。
        self.sw_anti = SwitchControl(bool(cfg.get("anti_dup_enabled", True)))
        self.spin_anti = QSpinBox(self.body)
        self.spin_anti.setRange(app_data.ANTI_DUP_MIN_HOURS, app_data.ANTI_DUP_MAX_HOURS)
        self.spin_anti.setValue(int(cfg.get("anti_dup_hours", 24)))
        self.spin_anti.setSuffix(" " + t("unit_hours"))
        # 跟着 QSS 的输入框最小高度（52）走：压到 44 会把上下内边距吃掉，
        # 文字贴着框顶、下方只剩一条 1px 底线，看着像被裁过。
        self.spin_anti.setMinimumHeight(52)
        self.spin_anti.setEnabled(self.sw_anti.isChecked())
        antial = QLabel(t("anti_label"), self.body)
        antial.setWordWrap(True)
        antial.setStyleSheet(f"color:{COLORS['ink']}; font-size:14px; background:transparent;")
        self.body_lay.addWidget(antial)
        anti_row = QHBoxLayout()
        anti_row.addStretch(1)
        anti_row.addWidget(self.spin_anti)
        anti_row.addSpacing(10)
        anti_row.addWidget(self.sw_anti)
        self.body_lay.addLayout(anti_row)
        self.sw_anti.toggled.connect(lambda ch: (self.spin_anti.setEnabled(ch),
                                                 m_bounce(self.spin_anti, s=0.90, dur=380)))

        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        save = self.add_action(t("set_save"), role="none", primary=True)
        save.clicked.connect(self._save)

    def _save(self):
        """保存：语言 + 防重设置，写盘并标记 applied。"""
        set_lang("en" if self.seg_lang.currentIndex() == 1 else "zh")
        cfg = self.store.load_config()
        cfg["anti_dup_enabled"] = self.sw_anti.isChecked()
        cfg["anti_dup_hours"] = self.spin_anti.value()
        self.store.save_config(cfg)
        self.cfg = cfg
        self.applied = True
        self.accept()

    def _run_wizard(self):
        """从设置进入配置向导（嵌套应用内弹窗）。"""
        wiz = SetupWizard(self.window(), self.store, self.store.load_config())
        if wiz.exec():
            self.cfg = self.store.load_config()
            self.applied = True


# ===========================================================================
# 管理员验证（删除记录前的密码门）
# ===========================================================================

class AdminPasswordDialog(MaterialDialog):
    """输入管理员密码；密码为编译期固定值（security.py），不写盘。"""

    def __init__(self, parent, title: str | None = None, hint: str | None = None):
        super().__init__(parent, title or t("admin_title"), card_width=440, scrim_cancel=True)
        self.verified = False

        tip = QLabel(hint or t("admin_hint"), self.body)
        tip.setWordWrap(True)
        tip.setStyleSheet(
            f"font-size:14px; color:{COLORS['on_surface_variant']}; background:transparent;")
        self.body_lay.addWidget(tip)

        self.edit = QLineEdit(self.body)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(t("admin_placeholder"))
        self.edit.setMinimumHeight(56)
        self.edit.setMaxLength(64)
        self.edit.setStyleSheet(
            f"QLineEdit {{ font-size:17px; letter-spacing:2px; padding:0 16px;"
            f" background:{COLORS['surface_container_lowest']};"
            f" border:1.4px solid {COLORS['outline']};"
            f" border-radius:12px; min-height:54px; }}"
            f"QLineEdit:focus {{ border-color:{COLORS['primary']};"
            f" background:{COLORS['surface_container_low']}; }}")
        self.body_lay.addWidget(self.edit)

        self.err = QLabel("", self.body)
        self.err.setStyleSheet(
            f"font-size:13px; color:{COLORS['error']}; background:transparent;")
        self.err.setVisible(False)
        self.body_lay.addWidget(self.err)

        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        ok = self.add_action(t("admin_ok"), role="none", primary=True)
        ok.clicked.connect(self._check)
        self.edit.returnPressed.connect(self._check)
        QTimer.singleShot(260, self.edit.setFocus)

    def _check(self):
        from . import security
        if security.verify(self.edit.text()):
            self.verified = True
            self.accept()
            return
        self.err.setText(t("admin_wrong"))
        self.err.setVisible(True)
        m_pop_in(self.err, dy=12, s=0.92, dur=420)     # 错误提示弹入
        m_bounce(self.edit, s=0.955, dur=360)          # 输入框弹性回弹
        m_burst(self.edit, COLORS["error"], max_r=120, dur=560)  # 红色光环扩散
        self.edit.selectAll()
        self.edit.setFocus()
        self._shake()

    def _shake(self):
        """错误反馈：卡片左右轻微抖动（M3 错误态）。

        走 MotionEffect 的 dx（像素位移），不再动画化布局管理的 pos——
        后者会被布局重排"拽回"原位，看起来就是横向突然跳一下。
        """
        m_shake(self.card, amp=10, dur=320)


# ===========================================================================
# 记录清理：按时间段删除（先归档，再移除）
# ===========================================================================

class HistoryCleanupDialog(MaterialDialog):
    """选择时间范围 → 预览条数 → 归档删除。所有控件按触摸大屏设计（>=48px）。"""

    def __init__(self, parent, store: ClassStore):
        super().__init__(parent, t("clean_title"), card_width=640, scrim_cancel=True)
        self.store = store
        self.deleted_count = 0
        self.archive_path = None
        self._preset = "today"

        bounds = store.history_bounds()
        self._bounds = bounds
        total = len(store.history())

        info = QLabel(f"该班级共 {total} 条记录" +
                      (f" · {bounds[0][:10]} ~ {bounds[1][:10]}" if bounds else ""), self.body)
        info.setStyleSheet(
            f"font-size:13px; color:{COLORS['on_surface_variant']}; background:transparent;")
        self.body_lay.addWidget(info)

        range_lab = QLabel(t("clean_range"), self.body)
        range_lab.setStyleSheet(
            f"font-size:15px; font-weight:600; color:{COLORS['on_surface']}; background:transparent;")
        self.body_lay.addWidget(range_lab)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chips = {}
        for key, label in (("today", t("clean_today")), ("7d", t("clean_7d")),
                           ("30d", t("clean_30d")), ("all", t("clean_all")),
                           ("custom", t("clean_custom"))):
            c = ChoiceChip(label, checked=(key == "today"), parent=self.body)
            c.clicked.connect(lambda _=False, k=key: self._use_preset(k))
            self.chips[key] = c
            chips.addWidget(c)
        chips.addStretch(1)
        self.body_lay.addLayout(chips)

        grid = QHBoxLayout()
        grid.setSpacing(12)
        col1 = QVBoxLayout()
        col1.setSpacing(6)
        l1 = QLabel(t("clean_start"), self.body)
        l1.setStyleSheet(f"font-size:12.5px; color:{COLORS['on_surface_variant']}; background:transparent;")
        self.dt_start = QDateTimeEdit(self.body)
        self.dt_start.setDisplayFormat("yyyy-MM-dd  HH:mm:ss")
        self.dt_start.setButtonSymbols(QDateTimeEdit.NoButtons)
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setMinimumHeight(52)
        self.dt_start.setMinimumWidth(240)
        col1.addWidget(l1)
        col1.addWidget(self.dt_start)

        col2 = QVBoxLayout()
        col2.setSpacing(6)
        l2 = QLabel(t("clean_end"), self.body)
        l2.setStyleSheet(f"font-size:12.5px; color:{COLORS['on_surface_variant']}; background:transparent;")
        self.dt_end = QDateTimeEdit(self.body)
        self.dt_end.setDisplayFormat("yyyy-MM-dd  HH:mm:ss")
        self.dt_end.setButtonSymbols(QDateTimeEdit.NoButtons)
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setMinimumHeight(52)
        self.dt_end.setMinimumWidth(240)
        col2.addWidget(l2)
        col2.addWidget(self.dt_end)

        grid.addLayout(col1, 1)
        grid.addLayout(col2, 1)
        self.body_lay.addLayout(grid)

        self.preview = QLabel("", self.body)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(
            f"font-size:15px; font-weight:500; color:{COLORS['vermilion']};"
            f" background:{COLORS['vermilion_soft']}; border-radius:8px; padding:12px 16px;")
        self.body_lay.addWidget(self.preview)

        warn = QLabel(t("clean_warn"), self.body)
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"font-size:12.5px; color:{COLORS['on_surface_variant']}; background:transparent;")
        self.body_lay.addWidget(warn)

        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        self.btn_delete = make_button(t("clean_btn"), "error", min_height=48)
        self.btn_delete.clicked.connect(self._do_delete)
        self.action_lay.addWidget(self.btn_delete)

        self.dt_start.dateTimeChanged.connect(lambda _: self._on_custom())
        self.dt_end.dateTimeChanged.connect(lambda _: self._on_custom())
        self._use_preset("today")

    # ------------------------------------------------------------ 区间
    def _use_preset(self, key: str):
        self._preset = key
        for k, c in self.chips.items():
            c.setChecked(k == key)
        now = QDateTime.currentDateTime()
        if key == "today":
            start = QDateTime(now.date(), QTime(0, 0, 0))
            end = QDateTime(now.date(), QTime(23, 59, 59))
        elif key == "7d":
            start = QDateTime(now.date().addDays(-6), QTime(0, 0, 0))
            end = QDateTime(now.date(), QTime(23, 59, 59))
        elif key == "30d":
            start = QDateTime(now.date().addDays(-29), QTime(0, 0, 0))
            end = QDateTime(now.date(), QTime(23, 59, 59))
        elif key == "all" and self._bounds:
            start = QDateTime.fromString(self._bounds[0], "yyyy-MM-dd HH:mm:ss")
            end = QDateTime.fromString(self._bounds[1], "yyyy-MM-dd HH:mm:ss")
        else:
            return self._update_preview()
        for w, v in ((self.dt_start, start), (self.dt_end, end)):
            w.blockSignals(True)
            w.setDateTime(v)
            w.blockSignals(False)
        self._update_preview()

    def _on_custom(self):
        self._preset = "custom"
        for k, c in self.chips.items():
            c.setChecked(k == "custom")
        self._update_preview()

    def _range(self) -> tuple[str, str]:
        return (self.dt_start.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
                self.dt_end.dateTime().toString("yyyy-MM-dd HH:mm:ss"))

    def _update_preview(self):
        start, end = self._range()
        total = len(self.store.history())
        if start > end:
            text, enabled = t("clean_invalid"), False
        else:
            n = self.store.count_history_range(start, end)
            if n <= 0:
                text, enabled = t("clean_preview_none"), False
            else:
                text, enabled = t("clean_preview_fmt", n=n, total=total), True
        m_flip(self.preview, text)   # 预览文案翻转切换；相同文案不闪
        if self.btn_delete.isEnabled() != enabled:
            self.btn_delete.setEnabled(enabled)
            m_bounce(self.btn_delete, s=0.90, dur=360)

    # ------------------------------------------------------------ 删除
    def _do_delete(self):
        start, end = self._range()
        if start > end:
            inform(self, t("clean_title"), t("clean_invalid"), warn=True)
            return
        n = self.store.count_history_range(start, end)
        if n <= 0:
            return
        if not ask(self, t("clean_title"), t("clean_confirm_fmt", n=n, start=start, end=end),
                   yes=t("clean_btn"), no=t("dlg_cancel")):
            return
        try:
            count, path = self.store.delete_history_range(start, end)
        except Exception:
            inform(self, t("clean_title"), t("clean_fail"), warn=True)
            return
        self.deleted_count = count
        self.archive_path = path
        self.accept()
