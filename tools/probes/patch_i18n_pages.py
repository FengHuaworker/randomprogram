# -*- coding: utf-8 -*-
"""开发脚本：把 ui_pages.py 文案接入语言表 t()（一次性批量替换）。"""

import io

p = r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\app\ui_pages.py'
s = io.open(p, encoding='utf-8').read()

reps = [
    ('snack(self, "摇号池为空：请检查人数配置、屏蔽名单或防重冷却"',
     'snack(self, t("snack_pool_empty")'),
    ('self.btn_toggle.setText("停止")', 'self.btn_toggle.setText(t("draw_stop"))'),
    ('self.btn_toggle.setText("开 始")', 'self.btn_toggle.setText(t("draw_start"))'),
    ('snack(self, "本轮还没有抽中记录，无需重置")',
     'snack(self, t("snack_reset_none"))'),
    ('if not ask(self, "重置本轮", f"确定要重置本轮吗？\\n\\n将清空本轮已抽 {n} 人与全部防重冷却记录，\\n"\n                   "所有人重新回到摇号池。\\n（永久抽号历史不受影响）", yes="重置", no="取消"):',
     'if not ask(self, t("draw_reset_round"), t("confirm_reset_fmt", n=n),\n                   yes=t("dlg_reset"), no=t("dlg_cancel")):'),
    ('snack(self, "已重置：所有人已回到摇号池")', 'snack(self, t("snack_reset_done"))'),
    ('snack(self, f"记录已导出 → exports\\\\{out.name}", kind="success")',
     'snack(self, t("snack_export_ok", name=out.name), kind="success")'),
    ('snack(self, "导出失败：exports 目录不可写，请检查软件所在文件夹权限。",',
     'snack(self, t("snack_export_fail"),'),
    ('t = QLabel("抽号记录")', 't = QLabel(t("history_title"))'),
    ('self.btn_export = make_button("导出为TXT", "primary", min_height=44)',
     'self.btn_export = make_button(t("export_txt"), "primary", min_height=44)'),
    ('self.table.setHorizontalHeaderLabels(["序号", "抽号时间", "抽中号码", "学生姓名", "模式"])',
     'self.table.setHorizontalHeaderLabels([t("col_no"), t("col_time"), t("col_num"), t("col_name"), t("col_mode")])'),
    ('t = QLabel("概率统计")', 't = QLabel(t("stats_title"))'),
    ('self.table.setHorizontalHeaderLabels(["排名", "号码 / 姓名", "抽中次数", "占比"])',
     'self.table.setHorizontalHeaderLabels([t("col_rank"), t("col_key"), t("col_count"), t("col_pct")])'),
    ('self.table.setHorizontalHeaderLabels(["排名", "号码 / 姓名", "抽中次数", "占比", ""])',
     'self.table.setHorizontalHeaderLabels([t("col_rank"), t("col_key"), t("col_count"), t("col_pct"), ""])'),
    ('title = QLabel("班级配置状态")', 'title = QLabel(t("config_title"))'),
    ('rtitle = QLabel("名单与导入")', 'rtitle = QLabel(t("roster_title"))'),
    ('hint = QLabel("高级模式名单：一行一个姓名，按学号顺序。"',
     'hint = QLabel(t("roster_hint")'),
    ('self.btn_edit_roster = make_button("编辑名单", "primary", min_height=44)',
     'self.btn_edit_roster = make_button(t("edit_roster"), "primary", min_height=44)'),
    ('t2 = QLabel("防重设置")', 't2 = QLabel(t("anti_title"))'),
    ('self.sw_anti_label = QLabel("启用防重：学生被抽中后，在设置的时间窗口内不再进入摇号池")',
     'self.sw_anti_label = QLabel(t("anti_label"))'),
    ('self.btn_reconfig = make_button("重新配置（引导向导）", "ghost", min_height=44)',
     'self.btn_reconfig = make_button(t("reconfig_btn"), "ghost", min_height=44)'),
    ('t = QLabel("屏蔽管理")', 't = QLabel(t("shield_title"))'),
    ('tip = QLabel("长期屏蔽：该学生永不进入摇号池（直到手动移出）。"\n                     "短期屏蔽：当天不进入摇号池，次日自动解除。选中表格中的学生后点按下方按钮批量操作。")',
     'tip = QLabel(t("shield_hint"))'),
    ('self.table.setHorizontalHeaderLabels(["状态", "学号", "学生姓名", "备注"])',
     'self.table.setHorizontalHeaderLabels([t("col_status"), t("col_num"), t("col_name"), t("note_never")])'),
    ('self.btn_add_long = make_button("添加到长期屏蔽", "", min_height=44)',
     'self.btn_add_long = make_button(t("add_long"), "", min_height=44)'),
    ('self.btn_rm_long = make_button("移出长期屏蔽", "ghost", min_height=44)',
     'self.btn_rm_long = make_button(t("rm_long"), "ghost", min_height=44)'),
    ('self.btn_add_short = make_button("添加到短期(今天)", "", min_height=44)',
     'self.btn_add_short = make_button(t("add_short"), "", min_height=44)'),
    ('self.btn_rm_short = make_button("移出短期", "ghost", min_height=44)',
     'self.btn_rm_short = make_button(t("rm_short"), "ghost", min_height=44)'),
    ('self.btn_clear_long = make_button("清空长期屏蔽", "danger", min_height=44)',
     'self.btn_clear_long = make_button(t("clear_long"), "danger", min_height=44)'),
    ('self.btn_clear_short = make_button("清空短期屏蔽", "danger", min_height=44)',
     'self.btn_clear_short = make_button(t("clear_short"), "danger", min_height=44)'),
    ('                status = "长期屏蔽"', '                status = t("status_long")'),
    ('                status = "短期屏蔽(今天)"', '                status = t("status_short")'),
    ('                status = "正常"', '                status = t("status_normal")'),
    ('self.summary.setText(\n            f"共 {len(students)} 名学生 · 长期屏蔽 {len(long_n)} 人 · "\n            f"今天短期屏蔽 {len(short_n)} 人（次日自动解除）")',
     'self.summary.setText(t("shield_summary", total=len(students), long=len(long_n), short=len(short_n)))'),
    ('title = "选择要长期屏蔽的学生" if kind == "long" else "选择今天要屏蔽的学生"',
     'title = t("pick_title_pre") if kind == "long" else t("pick_title_short")'),
    ('snack(self, "请先在表格中选中学生（可点击行或拖动批量选择）")',
     'snack(self, t("snack_select_first"))'),
    ('c3 = QTableWidgetItem("永不参与" if num in long_n else\n                                  ("截止今日24点" if num in short_n else ""))',
     'c3 = QTableWidgetItem(t("note_never") if num in long_n else\n                                  (t("note_today") if num in short_n else ""))'),
]

for old, new in reps:
    c = s.count(old)
    if c == 0:
        print('MISS:', old[:60].replace('\n', ' '))
        continue
    s = s.replace(old, new)
    print('ok:', c, old[:40].replace('\n', ' '))

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('DONE')
