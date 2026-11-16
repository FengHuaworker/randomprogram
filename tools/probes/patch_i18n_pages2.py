# -*- coding: utf-8 -*-
"""开发脚本：ui_pages.py 补标题引用与 retranslate 支持（一次性）。"""

import io

p = r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\app\ui_pages.py'
s = io.open(p, encoding='utf-8').read()

reps = [
    # HistoryPage：标题/按钮/说明引用
    ('        t = QLabel(t("history_title"))\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_title = QLabel(t("history_title"))\n        t = self._t_title\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    ('        tip = QLabel("记录无限期永久保存（不可删除），按时间倒序排列。")',
     '        self._t_tip = QLabel(t("history_hint"))\n        tip = self._t_tip'),
    # StatsPage
    ('        t = QLabel(t("stats_title"))\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_title = QLabel(t("stats_title"))\n        t = self._t_title\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    # ConfigPage
    ('        title = QLabel(t("config_title"))\n        title.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_title = QLabel(t("config_title"))\n        title = self._t_title\n        title.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    ('        rtitle = QLabel(t("roster_title"))\n        rtitle.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_rtitle = QLabel(t("roster_title"))\n        rtitle = self._t_rtitle\n        rtitle.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    ('        hint = QLabel(t("roster_hint")\n                \
               + "可直接编辑、追加、删除，保存后自动同步总人数。")',
     '        self._t_rhint = QLabel(t("roster_hint"))\n        hint = self._t_rhint'),
    ('        t2 = QLabel(t("anti_title"))\n        t2.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_anti_title = QLabel(t("anti_title"))\n        t2 = self._t_anti_title\n        t2.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    # ShieldPage
    ('        t = QLabel(t("shield_title"))\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_title = QLabel(t("shield_title"))\n        t = self._t_title\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    ('        tip = QLabel(t("shield_hint"))',
     '        self._t_tip = QLabel(t("shield_hint"))\n        tip = self._t_tip'),
]

for old, new in reps:
    c = s.count(old)
    if c == 0:
        print('MISS:', old[:70].replace('\n', ' '))
        continue
    assert c == 1, f"ambiguous({c}): {old[:50]}"
    s = s.replace(old, new)
    print('ok:', old[:44].replace('\n', ' '))

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('DONE')
