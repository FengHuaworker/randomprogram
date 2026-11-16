# -*- coding: utf-8 -*-
"""开发脚本：ui_dialogs.py 文案接入 t() 并追加 AppSettingsDialog。"""

import io

p = r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\app\ui_dialogs.py'
s = io.open(p, encoding='utf-8').read()

# ---- 1) 头部导入 ----
s = s.replace(
    "from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,\n"
    "                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,\n"
    "                               QListWidget, QListWidgetItem, QStackedWidget, QWidget,\n"
    "                               QFrame, QAbstractItemView, QHeaderView)",
    "from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,\n"
    "                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,\n"
    "                               QListWidget, QListWidgetItem, QStackedWidget, QWidget,\n"
    "                               QFrame, QAbstractItemView, QHeaderView, QRadioButton)")
s = s.replace(
    "from .theme import COLORS, serif_style",
    "from .lang import t, set_lang, get_lang\nfrom .theme import COLORS, serif_style")
s = s.replace(
    "from .ui_widgets import (make_button, ask, inform, MaterialDialog,\n"
    "                         AppFilePickerDialog, enable_touch_scroll)",
    "from .ui_widgets import (make_button, ask, inform, MaterialDialog,\n"
    "                         AppFilePickerDialog, enable_touch_scroll, SwitchControl)")

# ---- 2) ClassNameDialog ----
s = s.replace('self.edit.setPlaceholderText("例如：三年级1班")',
              'self.edit.setPlaceholderText(t("classname_placeholder"))')

# ---- 3) SetupWizard ----
s = s.replace('super().__init__(parent, f"配置引导 · {store.name}", card_width=560, scrim_cancel=True)',
              'super().__init__(parent, t("wizard_title_fmt", name=store.name), card_width=560, scrim_cancel=True)')
s = s.replace('self.card_simple = _OptionCard("简易模式", "只需输入班级人数，抽号只显示号码。最快上手。")',
              'self.card_simple = _OptionCard(t("mode_simple"), t("mode_simple_desc"))')
s = s.replace('self.card_advanced = _OptionCard("高级模式", "上传名单（一个姓名一行），抽号显示姓名，可用完整功能。")',
              'self.card_advanced = _OptionCard(t("mode_advanced"), t("mode_advanced_desc"))')
s = s.replace('v1.addWidget(QLabel("请输入班级总人数（正整数）："))',
              'v1.addWidget(QLabel(t("wiz_total")))')
s = s.replace('v2.addWidget(QLabel("该班级总人数（上传名单后将按名单人数自动校正）："))',
              'v2.addWidget(QLabel(t("wiz_total_adv")))')
s = s.replace('tip = QLabel("名单格式：一行一个姓名，按学号顺序排列（示例见 template/template.txt ）。")',
              'tip = QLabel(t("wiz_roster_tip"))')
s = s.replace('self.btn_pick = make_button("选择名单文件(.txt)", "primary", min_height=48)',
              'self.btn_pick = make_button(t("wiz_pick_file") + "(.txt)", "primary", min_height=48)')
s = s.replace('self.btn_tpl = make_button("下载示例模板", "ghost", min_height=44)',
              'self.btn_tpl = make_button(t("wiz_download_tpl"), "ghost", min_height=44)')
s = s.replace('self.roster_info = QLabel("尚未选择名单")',
              'self.roster_info = QLabel(t("wiz_roster_none"))')
s = s.replace('self.btn_back = self.add_action("上一步", role="none", primary=False)',
              'self.btn_back = self.add_action(t("wiz_prev"), role="none", primary=False)')
s = s.replace('self.add_action("取消", role="reject", primary=False)\n        self.btn_next = self.add_action("下一步", role="none", primary=True)',
              'self.add_action(t("dlg_cancel"), role="reject", primary=False)\n        self.btn_next = self.add_action(t("wiz_next"), role="none", primary=True)')
s = s.replace('self.step_label.setText("第 1 步 / 共 2 步 · 选择引导模式")',
              'self.step_label.setText(t("wiz_step1"))')
s = s.replace('self.step_label.setText(f"第 2 步 / 共 {3 if is_adv else 2} 步 · 设置班级人数")',
              'self.step_label.setText(t("wiz_step2", total=(3 if is_adv else 2)))')
s = s.replace('self.step_label.setText("第 3 步 / 共 3 步 · 上传班级名单")',
              'self.step_label.setText(t("wiz_step3"))')
s = s.replace('self.btn_next.setText("下一步")', 'self.btn_next.setText(t("wiz_next"))')
s = s.replace('self.btn_next.setText("完成")', 'self.btn_next.setText(t("wiz_done"))')
s = s.replace('self.roster_info.setText(f"已读取 {len(names)} 个姓名：")',
              'self.roster_info.setText(t("wiz_roster_loaded", n=len(names)))')
s = s.replace("inform(self, \"提示\", \"请先点击选择一种引导模式\")",
              "inform(self, t(\"app_title\"), t(\"wiz_pick_mode\"))")
s = s.replace('inform(self, "错误", "无法读取该文件，请确认是 UTF-8 或 GBK 编码的文本文件。", warn=True)',
              'inform(self, t("app_title"), t("wiz_read_fail"), warn=True)')
s = s.replace('inform(self, "错误", "文件中没有有效姓名（一行一个）。", warn=True)',
              'inform(self, t("app_title"), t("wiz_no_names"), warn=True)')
s = s.replace('inform(self, "模板已生成", f"示例模板已保存到：\\n{p}")',
              'inform(self, t("app_title"), t("wiz_tpl_done", path=p))')
s = s.replace('inform(self, "错误", "模板生成失败，请检查软件目录是否可写。", warn=True)',
              'inform(self, t("app_title"), t("wiz_tpl_fail"), warn=True)')

# ---- 4) RosterEditorDialog ----
s = s.replace('super().__init__(parent, f"名单编辑 · {store.name}", card_width=620, scrim_cancel=True)',
              'super().__init__(parent, t("roster_title_fmt", name=store.name), card_width=620, scrim_cancel=True)')
s = s.replace('hint = QLabel("直接在“姓名”列修改；学号自动按顺序编号。保存后立即生效。", self.body)',
              'hint = QLabel(t("roster_edit_hint"), self.body)')
s = s.replace('self.table.setHorizontalHeaderLabels(["学号", "姓名"])',
              'self.table.setHorizontalHeaderLabels([t("col_num"), t("col_name")])')
s = s.replace('self.btn_add = make_button("追加一行", "", min_height=44)',
              'self.btn_add = make_button(t("roster_add"), "", min_height=44)')
s = s.replace('self.btn_del = make_button("删除选中", "danger", min_height=44)',
              'self.btn_del = make_button(t("roster_del"), "danger", min_height=44)')
s = s.replace('self.btn_up = make_button("上移", "ghost", min_height=44)',
              'self.btn_up = make_button(t("roster_up"), "ghost", min_height=44)')
s = s.replace('self.btn_down = make_button("下移", "ghost", min_height=44)',
              'self.btn_down = make_button(t("roster_down"), "ghost", min_height=44)')
s = s.replace('self.btn_reupload = make_button("重新上传…", "ghost", min_height=44)',
              'self.btn_reupload = make_button(t("roster_reupload"), "ghost", min_height=44)')
s = s.replace('self.count_label = QLabel(f"共 {len(self._names)} 人", self.body)',
              'self.count_label = QLabel(t("roster_count_fmt", n=len(self._names)), self.body)')
s = s.replace('self.add_action("取消", role="reject", primary=False)\n        save = self.add_action("保存", role="none", primary=True)',
              'self.add_action(t("dlg_cancel"), role="reject", primary=False)\n        save = self.add_action(t("roster_save"), role="none", primary=True)')
s = s.replace('self.count_label.setText(f"共 {len(names)} 人")',
              'self.count_label.setText(t("roster_count_fmt", n=len(names)))')
s = s.replace('dlg = AppFilePickerDialog(self, "重新上传名单", start_dir=self.store.dir.parent.parent,',
              'dlg = AppFilePickerDialog(self, t("roster_reupload_title"), start_dir=self.store.dir.parent.parent,')

# ---- 5) StudentPickDialog ----
s = s.replace('self.search.setPlaceholderText("输入姓名或号码筛选…")',
              'self.search.setPlaceholderText(t("pick_search"))')
s = s.replace('all_btn = make_button("全选", "ghost", min_height=40)',
              'all_btn = make_button(t("pick_all"), "ghost", min_height=40)')
s = s.replace('none_btn = make_button("清空", "ghost", min_height=40)',
              'none_btn = make_button(t("pick_clear"), "ghost", min_height=40)')
s = s.replace('self.count_label = QLabel(f"已选 {len(preselected)} 人", self.body)',
              'self.count_label = QLabel(t("pick_count_fmt", n=len(preselected)), self.body)')
s = s.replace('self.add_action("取消", role="reject", primary=False)\n        self.add_action("确定", role="accept", primary=True)',
              'self.add_action(t("dlg_cancel"), role="reject", primary=False)\n        self.add_action(t("dlg_ok"), role="accept", primary=True)')
s = s.replace('item = QListWidgetItem(f"{num:02d}　{name if name else \'（未命名）\'}")',
              'item = QListWidgetItem(f"{num:02d}　{name if name else t(\'unnamed\')}")')
s = s.replace('self.count_label.setText(f"已选 {n} 人")',
              'self.count_label.setText(t("pick_count_fmt", n=n))')

# ---- 6) AppFilePickerDialog ----
s = s.replace('self.btn_up = make_button("上级目录", "ghost", min_height=40)',
              'self.btn_up = make_button(t("fp_up"), "ghost", min_height=40)')
s = s.replace('hint = QLabel(f"双击文件夹进入；点击文件后点「选择」。仅显示 {", ".join(suffixes)} 文件。",',
              'hint = QLabel(t("fp_hint_fmt", suffixes=(", ".join(suffixes))),')
s = s.replace('self.btn_ok = self.add_action("选择", role="none", primary=True)',
              'self.btn_ok = self.add_action(t("fp_choose"), role="none", primary=True)')
s = s.replace('self.add_action("取消", role="reject", primary=False)\n\n        self._fill()',
              'self.add_action(t("dlg_cancel"), role="reject", primary=False)\n\n        self._fill()')
s = s.replace('self.listw.addItem("（无法访问该目录）")',
              'self.listw.addItem(t("fp_cannot"))')
s = s.replace('self.listw.addItem("（空目录）")', 'self.listw.addItem(t("fp_empty"))')

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('replaced done')

# ---- 7) 追加 AppSettingsDialog ----
APPEND = '''

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
        self.spin_anti.setMinimumHeight(44)
        self.spin_anti.setEnabled(self.sw_anti.isChecked())
        anti_row.addWidget(QLabel(t("anti_label"), self.body), 1)
        anti_row.addWidget(self.spin_anti)
        anti_row.addSpacing(10)
        anti_row.addWidget(self.sw_anti)
        antial = QLabel(t("anti_label"), self.body)
        antial.setWordWrap(True)
        antial.setStyleSheet(f"color:{COLORS['ink']}; font-size:14px; background:transparent;")
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
'''
s2 = io.open(p, encoding='utf-8').read()
if 'class AppSettingsDialog' not in s2:
    s2 += APPEND
    io.open(p, 'w', encoding='utf-8', newline='').write(s2)
    print('appended AppSettingsDialog')
else:
    print('AppSettingsDialog exists')
