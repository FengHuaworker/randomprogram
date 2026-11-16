# -*- coding: utf-8 -*-
"""开发脚本：隐藏各列表格的多余垂直行号表头（已有序号/学号列）。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "app" / "ui_pages.py"
DIALOGS = ROOT / "app" / "ui_dialogs.py"

NEW_LINE = "        self.table.verticalHeader().setVisible(False)  # 已有序号列"

# ui_pages.py：HistoryPage / StatsPage / ShieldPage 三处表格都隐藏垂直表头
text = PAGES.read_text(encoding="utf-8")
anchor = "        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)"
n = text.count(anchor)
assert n == 3, f"ui_pages.py 锚点出现 {n} 次（应为 3）"
text = text.replace(anchor, anchor + "\n" + NEW_LINE)
PAGES.write_text(text, encoding="utf-8")
print(f"patched ui_pages.py ({n} 处)")

# ui_dialogs.py：名单编辑器
text = DIALOGS.read_text(encoding="utf-8")
anchor = ("        self.table.setEditTriggers("
          "QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)")
n = text.count(anchor)
assert n == 1, f"ui_dialogs.py 锚点出现 {n} 次（应为 1）"
text = text.replace(anchor, anchor + "\n" + NEW_LINE)
DIALOGS.write_text(text, encoding="utf-8")
print(f"patched ui_dialogs.py ({n} 处)")
