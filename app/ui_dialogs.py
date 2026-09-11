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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QListWidget, QListWidgetItem, QStackedWidget, QWidget,
                               QFrame, QAbstractItemView, QHeaderView, QRadioButton)

from . import app_data
from .app_data import ClassStore, MODE_SIMPLE, MODE_ADVANCED, ANTI_DUP_DEFAULT_HOURS
from .lang import t, set_lang, get_lang
from .theme import COLORS, serif_style
from .ui_widgets import (make_button, ask, inform, MaterialDialog,
                         AppFilePickerDialog, enable_touch_scroll, SwitchControl)


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
        self._selected = sel
        self._apply_style()

    def is_checked(self) -> bool:
        return self._selected

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(
                'QFrame[optCard="true"] { background:#E8EDF3; border:1px solid #8BA8C7;'
                ' border-left:5px solid #8BA8C7; border-radius:12px; }')
        else:
            self.setStyleSheet(
                'QFrame[optCard="true"] { background:#FBF8F4; border:1px solid #E3DCD2;'
                ' border-radius:12px; }'
                'QFrame[optCard="true"]:hover { background:#F6F1EB; }')


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
        self.roster_prev.setWordWrap(True)
        self.roster_prev.setStyleSheet(
            f"font-size:12px; color:{COLORS['ink_soft']}; background:{COLORS['paper_deep']};"
            "border-radius:8px; padding:10px;")
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
        st = self._state
        if st == "mode":
            self.stack.setCurrentIndex(0)
            self.step_label.setText(t("wiz_step1"))
            self.btn_back.setEnabled(False)
            self.btn_next.setEnabled(True)
            self.btn_next.setText(t("wiz_next"))
        elif st == "count":
            is_adv = self.card_advanced.is_checked()
            self.stack.setCurrentIndex(1 if not is_adv else 2)
            self.step_label.setText(t("wiz_step2", total=(3 if is_adv else 2)))
            self.btn_back.setEnabled(True)
            self.btn_next.setText(t("wiz_next"))
            self.btn_next.setEnabled(True)
        elif st == "roster":
            self.stack.setCurrentIndex(3)
            self.step_label.setText(t("wiz_step3"))
            self.btn_back.setEnabled(True)
            self.btn_next.setText(t("wiz_done"))
            self.btn_next.setEnabled(bool(self._roster))

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
            shown = "\n".join(names[:6]) + ("\n……" if len(names) > 6 else "")
            self.roster_info.setText(t("wiz_roster_loaded", n=len(names)))
            self.roster_prev.setText(shown)
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
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setMinimumHeight(360)
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

    def _del(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._renumber()

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
            self.count_label.setText(t("roster_count_fmt", n=len(names)))

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
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if num in self._pre else Qt.Unchecked)
            self.listw.addItem(item)
        self._refresh_count()

    def _refresh_count(self):
        lbl = getattr(self, "count_label", None)
        if lbl is None:
            return
        lbl.setText(t("pick_count_fmt", n=len(self.selected())))

    def _set_all(self, state):
        for i in range(self.listw.count()):
            self.listw.item(i).setCheckState(state)
        self._refresh_count()

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
        super().__init__(parent, t("settings_title"), card_width=480, scrim_cancel=True)
        self.store = store
        self.cfg = dict(cfg)
        self.applied = False

        # ---- 界面语言 ----
        lang_lab = QLabel(t("set_lang"), self.body)
        lang_lab.setStyleSheet(serif_style(16, COLORS["ink"], 600) + "; background:transparent;")
        self.body_lay.addWidget(lang_lab)
        lang_row = QHBoxLayout()
        self.rb_zh = QRadioButton(t("lang_zh"), self.body)
        self.rb_en = QRadioButton(t("lang_en"), self.body)
        self.rb_zh.setChecked(get_lang() == "zh")
        self.rb_en.setChecked(get_lang() == "en")
        lang_row.addWidget(self.rb_zh)
        lang_row.addWidget(self.rb_en)
        lang_row.addStretch(1)
        self.body_lay.addLayout(lang_row)

        # ---- 引导模式入口 ----
        mode_lab = QLabel(t("set_mode"), self.body)
        mode_lab.setStyleSheet(serif_style(16, COLORS["ink"], 600) + "; background:transparent;")
        self.body_lay.addWidget(mode_lab)
        self.btn_wizard = make_button(t("run_wizard"), "ghost", min_height=44)
        self.btn_wizard.clicked.connect(self._run_wizard)
        self.body_lay.addWidget(self.btn_wizard)

        # ---- 防重设置 ----
        anti_lab = QLabel(t("set_anti"), self.body)
        anti_lab.setStyleSheet(serif_style(16, COLORS["ink"], 600) + "; background:transparent;")
        self.body_lay.addWidget(anti_lab)
        anti_row = QHBoxLayout()
        self.sw_anti = SwitchControl(bool(cfg.get("anti_dup_enabled", True)))
        self.spin_anti = QSpinBox(self.body)
        self.spin_anti.setRange(app_data.ANTI_DUP_MIN_HOURS, app_data.ANTI_DUP_MAX_HOURS)
        self.spin_anti.setValue(int(cfg.get("anti_dup_hours", 24)))
        self.spin_anti.setSuffix(" " + t("unit_hours"))
        self.spin_anti.setMinimumHeight(44)
        self.spin_anti.setEnabled(self.sw_anti.isChecked())
        antial = QLabel(t("anti_label"), self.body)
        antial.setWordWrap(True)
        antial.setStyleSheet(f"color:{COLORS['ink']}; font-size:14px; background:transparent;")
        anti_row.addWidget(antial, 1)
        anti_row.addWidget(self.spin_anti)
        anti_row.addSpacing(10)
        anti_row.addWidget(self.sw_anti)
        self.body_lay.addLayout(anti_row)
        self.sw_anti.toggled.connect(lambda ch: self.spin_anti.setEnabled(ch))

        self.add_action(t("dlg_cancel"), role="reject", primary=False)
        save = self.add_action(t("set_save"), role="none", primary=True)
        save.clicked.connect(self._save)

    def _save(self):
        """保存：语言 + 防重设置，写盘并标记 applied。"""
        set_lang("en" if self.rb_en.isChecked() else "zh")
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
