# -*- coding: utf-8 -*-
"""修复 ui_pages.py 局部变量 t 遮蔽 lang.t 的问题。"""

import io

p = r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\app\ui_pages.py'
s = io.open(p, encoding='utf-8').read()

reps = [
    # History / Stats 共用句式：head.addWidget(t) 后接 summary
    ('        t = self._t_title\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))',
     '        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))'),
    ('        head.addWidget(t)\n        head.addWidget(self.summary)',
     '        head.addWidget(self._t_title)\n        head.addWidget(self.summary)'),
    # ConfigPage
    ('        title = self._t_title\n        title.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        v.addWidget(title)',
     '        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        v.addWidget(self._t_title)'),
    ('        rtitle = self._t_rtitle\n        rtitle.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        vv.addWidget(rtitle)',
     '        self._t_rtitle.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        vv.addWidget(self._t_rtitle)'),
    ('        t2 = self._t_anti_title\n        t2.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        v2.addWidget(t2)',
     '        self._t_anti_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        v2.addWidget(self._t_anti_title)'),
    # ShieldPage
    ('        t = self._t_title\n        t.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        head.addWidget(t)',
     '        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))\n        head.addWidget(self._t_title)'),
]

for old, new in reps:
    c = s.count(old)
    if c == 0:
        print('MISS:', old[:60].replace('\n', ' '))
        continue
    s = s.replace(old, new)
    print('ok:', c, old[:44].replace('\n', ' '))

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('DONE')
