# -*- coding: utf-8 -*-
"""
页面层：抽号主界面 / 抽号记录 / 概率统计 / 配置展示 / 屏蔽管理。
每个页面通过 set_store(store) 切换班级并 refresh() 刷新数据。
"""

from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QTableWidget, QTableWidgetItem,
                               QScrollArea, QGridLayout, QProgressBar, QFrame,
                               QAbstractItemView, QHeaderView)

from . import app_data
from .app_data import ClassStore, MODE_ADVANCED, MODE_SIMPLE
from .lang import t
from .theme import COLORS, serif_style, FONT_SERIF
from .ui_widgets import (PaperCard, make_button, ZoomLabel, Halo, Badge, elastic_zoom,
                         start_halo, stop_halo, flash_halo, tick_pulse, ask, inform,
                         DotDivider, fade_slide_in, fade_in, flash_item_background,
                         animate_progress, enable_touch_scroll, snack, SwitchControl)


# ===========================================================================
# 背景装饰色块（有机形状，供视差/氛围使用）
# ===========================================================================

class _Blob(QWidget):
    """低透明有机色块：椭圆或大圆角矩形，可旋转（手工感装饰）。"""

    def __init__(self, color: str, alpha: int, w: float, h: float, rot: float = 0.0,
                 shape: str = "ellipse", parent=None):
        super().__init__(parent)
        self.setFixedSize(int(w), int(h))
        self._c = QColor(color)
        self._c.setAlpha(alpha)
        self._rot = rot
        self._shape = shape
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self._rot)
        p.setPen(Qt.NoPen)
        p.setBrush(self._c)
        r = QRectF(-self.width() / 2, -self.height() / 2, self.width(), self.height())
        if self._shape == "ellipse":
            p.drawEllipse(r)
        else:
            p.drawRoundedRect(r, 26, 26)
        p.end()


# ===========================================================================
# 抽号主界面
# ===========================================================================

class DrawPage(QWidget):
    """核心抽号页：数字滚动动画 + 开始/停止 + 本轮已抽 + 摇号池预览。"""

    TICK_MS = 60            # 数字跳动间隔 60ms（50~100ms 区间）
    STOP_ANIM_MS = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self._pool: list[dict] = []      # 当前摇号池
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._halo_anim = None
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 10)
        root.setSpacing(14)

        # ---------- 左侧：抽号核心区 ----------
        left = QVBoxLayout()
        left.setSpacing(12)

        self.result_card = PaperCard(click_ripple=True, hover_shine=True)
        self.result_card.setMinimumHeight(300)
        self.result_card.setCursor(Qt.PointingHandCursor)
        self.result_card.setToolTip("抽号进行中时，点击此区域立即停止")
        self.result_card.mousePressEvent = self._on_card_press  # 触屏/鼠标均可停止

        rc = QVBoxLayout(self.result_card)
        rc.setContentsMargins(20, 18, 20, 18)
        rc.setSpacing(4)

        self.halo = Halo(self.result_card)
        self.halo.raise_()
        self.result_card.installEventFilter(self)   # 卡片缩放时同步光晕尺寸

        rc.addStretch(2)
        self.num_label = ZoomLabel("—", self.result_card)
        self.num_label.set_scale(1.0)
        self.num_label.setAlignment(Qt.AlignCenter)
        # 大号数字用衬线体（杂志感），随位数自动调整字号
        self.num_label.setStyleSheet(
            f"font-family:{FONT_SERIF}; color:{COLORS['ink']}; font-weight:600; font-size:150px;")
        self.num_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        rc.addWidget(self.num_label, 0, Qt.AlignHCenter)

        self.name_label = ZoomLabel(t("name_placeholder"), self.result_card)
        self.name_label.set_scale(1.0)
        self.name_label.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:21px;")
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        rc.addWidget(self.name_label, 0, Qt.AlignHCenter)

        self.hint_label = QLabel("")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:13px;")
        rc.addWidget(self.hint_label)
        rc.addStretch(2)
        left.addWidget(self.result_card, 1)

        # 操作按钮行：中央圆角矩形大按钮（开始/停止），两侧次要操作
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_toggle = make_button(t("draw_start"), "fab", min_height=64)
        self.btn_toggle.setFixedSize(176, 64)
        self.btn_toggle.clicked.connect(self.toggle)
        self.btn_reset = make_button(t("draw_reset_round"), "danger", min_height=48)
        self.btn_reset.clicked.connect(self._reset_round)
        self.btn_export = make_button(t("draw_export"), "", min_height=48)
        self.btn_export.clicked.connect(self._export)
        btns.addStretch(1)
        btns.addWidget(self.btn_reset)
        btns.addSpacing(28)
        btns.addWidget(self.btn_toggle)
        btns.addSpacing(28)
        btns.addWidget(self.btn_export)
        btns.addStretch(1)
        left.addLayout(btns)
        root.addLayout(left, 5)

        # ---------- 右侧：本轮已抽 + 摇号池 ----------
        right = QVBoxLayout()
        right.setSpacing(12)

        # 本轮已抽
        self.card_round = PaperCard(hover_shine=True)
        card_round = self.card_round
        vr = QVBoxLayout(card_round)
        vr.setContentsMargins(16, 12, 16, 12)
        vr.setSpacing(8)
        tr = QHBoxLayout()
        t_round = QLabel(t("round_title"))
        t_round.setProperty("cardTitle", True)
        self._t_round = t_round
        self.round_count = QLabel("0 人")
        self.round_count.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:12px;")
        tr.addWidget(t_round)
        tr.addStretch(1)
        tr.addWidget(self.round_count)
        vr.addLayout(tr)
        self.round_list = QListWidget()
        self.round_list.setSelectionMode(QAbstractItemView.NoSelection)
        enable_touch_scroll(self.round_list)
        vr.addWidget(self.round_list, 1)
        right.addWidget(card_round, 3)

        # 摇号池预览
        self.card_pool = PaperCard(hover_shine=True)
        card_pool = self.card_pool
        vp = QVBoxLayout(card_pool)
        vp.setContentsMargins(16, 12, 16, 12)
        vp.setSpacing(8)
        tp = QHBoxLayout()
        t_pool = QLabel(t("pool_title"))
        t_pool.setProperty("cardTitle", True)
        self._t_pool = t_pool
        tp.addWidget(t_pool)
        tp.addStretch(1)
        vp.addLayout(tp)

        badges = QHBoxLayout()
        self.badge_ok = Badge("", "green")
        self.badge_block = Badge("", "pink")
        self.badge_cool = Badge("", "warm")
        badges.addWidget(self.badge_ok)
        badges.addWidget(self.badge_block)
        badges.addWidget(self.badge_cool)
        vp.addLayout(badges)

        self.pool_list = QListWidget()
        self.pool_list.setSelectionMode(QAbstractItemView.NoSelection)
        enable_touch_scroll(self.pool_list)
        vp.addWidget(self.pool_list, 1)
        right.addWidget(card_pool, 2)

        root.addLayout(right, 3)

    # ------------------------------------------------------------- 逻辑
    def set_store(self, store: ClassStore, cfg: dict):
        """切换班级：停止一切进行中的抽号，重载数据，并播放入场动画。"""
        self.stop_silent()
        self.store = store
        self.cfg = cfg
        self._prev_round_len = 0
        self.refresh()
        self.play_entrance()

    def play_entrance(self):
        """主界面入场：各卡片从不同方向交错滑入 + 淡入（交错节奏感）。"""
        fade_slide_in(self.result_card, dx=0, dy=22, dur=340, delay=40)
        fade_slide_in(self.btn_toggle, dy=14, dur=280, delay=360)
        fade_slide_in(self.btn_reset, dy=14, dur=280, delay=400)
        fade_slide_in(self.btn_export, dy=14, dur=280, delay=440)
        fade_slide_in(self.card_round, dx=26, dy=0, dur=340, delay=200)
        fade_slide_in(self.card_pool, dx=26, dy=0, dur=340, delay=270)

    def retranslate(self):
        """语言切换：更新卡片标题/按钮/提示并刷新数据。"""
        self._t_round.setText(t("round_title"))
        self._t_pool.setText(t("pool_title"))
        self.btn_reset.setText(t("draw_reset_round"))
        self.btn_export.setText(t("draw_export"))
        self.btn_toggle.setText(t("draw_stop") if self._running else t("draw_start"))
        if not self._running and not self.num_label.text():
            self.name_label.setText(t("name_placeholder"))
        self.refresh()

    def refresh(self):
        """刷新本轮列表、摇号池、按钮可用性。"""
        if self.store is None:
            return
        self._pool = self.store.draw_pool(self.cfg)
        self._refresh_round()
        self._refresh_pool()
        self._refresh_hint()

    def _refresh_round(self):
        items = self.store.round_list() if self.store else []
        prev = getattr(self, "_prev_round_len", 0)
        self.round_list.clear()
        for i, it in enumerate(items, 1):
            name = it.get("name") or f"#{int(it.get('num', 0)):02d}"
            self.round_list.addItem(f"{i:02d}　{name}")
            # 新抽中的条目：莫兰迪蓝高亮渐隐（点名感反馈）
            if i > prev:
                flash_item_background(self.round_list.item(i - 1),
                                      QColor(COLORS["blue_soft"]), dur=1000)
        self._prev_round_len = len(items)
        self.round_count.setText(f"{len(items)} 人")

    def _refresh_pool(self):
        if not self.store:
            return
        students = self.store.get_students(self.cfg)
        long_set = set(self.store.long_exempt())
        short_set = set(self.store.short_exempt())
        cool_set = set(self.store.cooling_nums(self.cfg))
        pool = self._pool
        pool_nums = {s["num"] for s in pool}
        blocked = [s for s in students if s["num"] in long_set or s["num"] in short_set]
        cooling = [s for s in students if s["num"] in cool_set]
        self.badge_ok.setText(t("pool_ok", n=len(pool)))
        self.badge_block.setText(t("pool_block", long=len(long_set), short=len(short_set)))
        self.badge_cool.setText(t("pool_cool", n=len(cooling)))
        self.pool_list.clear()
        for s in pool[:40]:
            name = s.get("name") or ""
            self.pool_list.addItem(f"{s['num']:02d}　{name if name else t('unnamed')}")
        if len(pool) > 40:
            self.pool_list.addItem(f"…… 共 {len(pool)} 人")
        # 可用数少于人数时标记哪些在别处（不展开，保持清爽）

    def _refresh_hint(self):
        total = self.cfg.get("total_count", 0)
        n_pool = len(self._pool)
        anti_on = self.cfg.get("anti_dup_enabled", True)
        if total == 0:
            self.hint_label.setText(t("hint_no_config"))
        elif n_pool == 0:
            self.hint_label.setText(t("hint_empty"))
        else:
            extra = ""
            if not anti_on:
                extra = t("hint_anti_off")
            elif self.cfg.get("mode") == MODE_ADVANCED:
                extra = t("hint_advanced")
            self.hint_label.setText(t("hint_pool", n=n_pool, extra=extra))
        self.btn_toggle.setEnabled(n_pool > 0)
        if n_pool == 0 or total == 0:
            self.btn_toggle.setText(t("draw_start"))

    # --------------------------------------------------------- 抽号流程
    def toggle(self):
        """开始/停止切换（按钮、空格键、点按结果区共用）。"""
        if not self.store:
            return
        if self._running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.store:
            return
        self._pool = self.store.draw_pool(self.cfg)
        if not self._pool:
            snack(self, t("snack_pool_empty"),
                  duration=3600)
            self.refresh()
            return
        self._running = True
        self.btn_toggle.setText(t("draw_stop"))
        self.num_label.setText("")
        # 回到“滚动态”样式：墨色 + 按位数自适应字号
        self.num_label.set_text_color(COLORS["ink"])
        self._apply_num_size(2)
        start_halo(self.halo)
        self._timer.start()
        # 立即跳动一次，避免延迟感
        self._tick()

    def _apply_num_size(self, digits: int):
        """按位数自适应衬线大数字字号（2 位 150px，3 位及以上 108px）。"""
        size = 150 if digits <= 2 else 108
        self.num_label.setStyleSheet(
            f"font-family:{FONT_SERIF}; color:{COLORS['ink']}; font-weight:600; font-size:{size}px;")

    def _tick(self):
        if not self._running or not self._pool:
            return
        s = random.choice(self._pool)
        self._show(s, rolling=True)

    def _show(self, s: dict, rolling: bool):
        num = s["num"]
        self.num_label.setText(f"{num:02d}" if num < 100 else str(num))
        self._apply_num_size(3 if num >= 100 else 2)
        if self.cfg.get("mode") == MODE_ADVANCED:
            self.name_label.setText(s.get("name") or "")
        else:
            self.name_label.setText("")
        if rolling and self._running:
            # 每一跳的微脉冲：数字“弹跳”滚动（老虎机的机械感）
            old = getattr(self, "_tick_anim", None)
            if old:
                old.stop()
            tick_pulse(self.num_label).start()

    def stop(self):
        """停止抽号并落盘记录（定格即结果）。"""
        if not self._running:
            return
        self._timer.stop()
        self._running = False
        stop_halo(self.halo)
        self.btn_toggle.setText(t("draw_start"))

        # 定格：当前显示的数字就是结果
        cur = self._current()
        if cur is None:
            self.refresh()
            return
        num, name = cur["num"], cur.get("name", "")
        result = self.store
        result.add_history(num, name, self.cfg.get("mode", MODE_SIMPLE))
        result.append_round(num, name)
        if self.cfg.get("anti_dup_enabled", True):
            result.record_cooling(num)

        # 定格弹性动画：1.0 → 1.1 → 1.0（OutBack 自然过冲）+ 光晕闪光
        self.num_label.set_text_color(COLORS["blue_dark"])
        elastic_zoom(self.num_label, start=0.86, dur=self.STOP_ANIM_MS).start()
        if name:
            self.name_label.set_text_color(COLORS["ink"])
            elastic_zoom(self.name_label, start=0.9, dur=self.STOP_ANIM_MS).start()
        flash_halo(self.halo, dur=640)

        self.refresh()
        # 徽章数字变化反馈：轻微呼吸
        self.badge_ok.pulse()
        self.badge_cool.pulse()

    def _current(self) -> dict | None:
        """读取当前显示的数字，并从摇号池中找到对应学生。"""
        text = self.num_label.text()
        try:
            num = int(text.lstrip("0")) if text.lstrip("0") else int(text or "0")
        except ValueError:
            num = 0
        for s in self._pool:
            if s["num"] == num:
                return s
        return None

    def stop_silent(self):
        """没有任何记录的强制停止（切班级时用）。"""
        if self._running:
            self._timer.stop()
            self._running = False
            stop_halo(self.halo)
        self.btn_toggle.setText(t("draw_start"))

    def _on_card_press(self, ev: QMouseEvent):
        # 触点涟漪反馈（鼠标/触屏一致）
        try:
            self.result_card.ripple_at(ev.position())
        except Exception:
            pass
        if self._running:
            self.stop()
        else:
            self.toggle()

    def eventFilter(self, obj, event):
        """结果卡片尺寸变化时，让光晕铺满卡片。"""
        if obj is self.result_card and event.type() == event.Type.Resize:
            self.halo.setGeometry(self.result_card.rect())
        return super().eventFilter(obj, event)

    # -------------------------------------------------------- 操作按钮
    def _reset_round(self):
        if not self.store:
            return
        n = len(self.store.round_list())
        if n == 0:
            snack(self, t("snack_reset_none"))
            return
        if not ask(self, t("draw_reset_round"), t("confirm_reset_fmt", n=n),
                   yes=t("dlg_reset"), no=t("dlg_cancel")):
            return
        self.store.reset_round()
        self.refresh()
        snack(self, t("snack_reset_done"))

    def _export(self):
        if not self.store:
            return
        text = self.store.export_text()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.store.dir.parent.parent / "exports" / \
              f"{app_data.safe_filename(self.store.name)}_记录_{ts}.txt"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            snack(self, t("snack_export_ok", name=out.name), kind="success")
        except Exception:
            snack(self, t("snack_export_fail"),
                  kind="error", duration=4200)


# ===========================================================================
# 抽号记录页
# ===========================================================================

class HistoryPage(QWidget):
    """永久抽号记录（时间倒序、滚动浏览、导出为 TXT）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 10)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self._t_title = QLabel(t("history_title"))
        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:13px;")
        self.btn_export = make_button(t("export_txt"), "primary", min_height=44)
        self.btn_export.clicked.connect(self._export)
        head.addWidget(self._t_title)
        head.addWidget(self.summary)
        head.addStretch(1)
        head.addWidget(self.btn_export)
        lay.addLayout(head)

        self._t_tip = QLabel(t("history_hint"))
        tip = self._t_tip
        tip.setStyleSheet(f"color:{COLORS['ink_faint']}; font-size:12px;")
        lay.addWidget(tip)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([t("col_no"), t("col_time"), t("col_num"), t("col_name"), t("col_mode")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)  # 已有序号列
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        enable_touch_scroll(self.table)
        lay.addWidget(self.table, 1)

    def set_store(self, store: ClassStore):
        self.store = store
        self.refresh()
        fade_slide_in(self.table, dx=18, dy=0, dur=300, delay=80)
        fade_slide_in(self.btn_export, dy=10, dur=260, delay=40)

    def retranslate(self):
        self._t_title.setText(t("history_title"))
        self._t_tip.setText(t("history_hint"))
        self.btn_export.setText(t("export_txt"))
        self.table.setHorizontalHeaderLabels(
            [t("col_no"), t("col_time"), t("col_num"), t("col_name"), t("col_mode")])
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        records = self.store.history()
        self.table.setRowCount(0)
        rows = list(reversed(records))          # 时间倒序：最新在前
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            c0 = QTableWidgetItem(str(i + 1))
            c1 = QTableWidgetItem(str(r.get("time", "")))
            c2 = QTableWidgetItem(str(int(r.get("num", 0))).zfill(2))
            c2.setTextAlignment(Qt.AlignCenter)
            c3 = QTableWidgetItem(r.get("name") or "—")
            c4 = QTableWidgetItem("高级" if r.get("mode") == MODE_ADVANCED else "简易")
            c4.setTextAlignment(Qt.AlignCenter)
            for ci, c in enumerate((c0, c1, c2, c3, c4)):
                self.table.setItem(i, ci, c)
        self.summary.setText(f"共 {len(records)} 条历史记录")

    def _export(self):
        if not self.store:
            return
        text = self.store.export_text()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.store.dir.parent.parent / "exports" / \
              f"{app_data.safe_filename(self.store.name)}_记录_{ts}.txt"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            snack(self, t("snack_export_ok", name=out.name), kind="success")
        except Exception:
            snack(self, t("snack_export_fail"),
                  kind="error", duration=4200)


# ===========================================================================
# 概率统计页
# ===========================================================================

class StatsPage(QWidget):
    """按号码（简易模式）/ 学生姓名（高级模式）统计抽中次数与概率。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 10)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self._t_title = QLabel(t("stats_title"))
        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:13px;")
        head.addWidget(self._t_title)
        head.addStretch(1)
        head.addWidget(self.summary)
        lay.addLayout(head)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([t("col_rank"), t("col_key"), t("col_count"), t("col_pct")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)  # 已有序号列
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        enable_touch_scroll(self.table)
        lay.addWidget(self.table, 1)

    def set_store(self, store: ClassStore):
        self.store = store
        self.refresh()
        fade_slide_in(self.table, dx=18, dy=0, dur=300, delay=80)

    def retranslate(self):
        self._t_title.setText(t("stats_title"))
        self.table.setHorizontalHeaderLabels(
            [t("col_rank"), t("col_key"), t("col_count"), t("col_pct"), ""])
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        items = self.store.stats()
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([t("col_rank"), t("col_key"), t("col_count"), t("col_pct"), ""])
        self.table.setRowCount(len(items))
        for i, s in enumerate(items):
            c0 = QTableWidgetItem(str(s["rank"]))
            c0.setTextAlignment(Qt.AlignCenter)
            c1 = QTableWidgetItem(s["display"])
            c2 = QTableWidgetItem(str(s["count"]))
            c2.setTextAlignment(Qt.AlignCenter)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            bar.setStyleSheet(
                f"QProgressBar {{ background:{COLORS['paper_deep']}; border:none; border-radius:5px; }}"
                f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {COLORS['green']}, stop:1 {COLORS['blue']}); border-radius:5px; }}")
            c3 = QTableWidgetItem(f"{s['pct']:.1f}%")
            c3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, c0)
            self.table.setItem(i, 1, c1)
            self.table.setItem(i, 2, c2)
            self.table.setCellWidget(i, 3, bar)
            self.table.setItem(i, 4, QTableWidgetItem(f"{s['pct']:.1f}%"))
            # 进度条从 0 增长到实际占比（逐行错峰，一次排开更有节奏感）
            animate_progress(bar, int(min(100, s["pct"])), dur=400, delay=100 + i * 60)
        total = sum(s["count"] for s in items)
        self.summary.setText(f"总抽号次数：{total} 次")


# ===========================================================================
# 配置展示页
# ===========================================================================

class ConfigPage(QWidget):
    """完整展示当前班级配置 + 名单编辑 / 重新配置入口。
    settings_changed：防重等设置被修改（供主窗口联动刷新摇号池等）。"""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self.on_reconfigure = None      # 回调：重新配置
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 12, 18, 10)
        outer.setSpacing(10)

        self.scroll = QScrollArea()
        scroll = self.scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # 显式选择器（避免无选择器声明沿继承链污染后代按钮背景）
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        enable_touch_scroll(scroll)
        self.inner = QWidget()
        inner = self.inner
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)

        self.cfg_card = PaperCard()
        card = self.cfg_card
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)
        self._t_title = QLabel(t("config_title"))
        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))
        v.addWidget(self._t_title)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(10)
        v.addLayout(self.grid)
        lay.addWidget(card)

        # 名单编辑面板
        self.roster_card = PaperCard()
        vv = QVBoxLayout(self.roster_card)
        vv.setContentsMargins(20, 16, 20, 16)
        vv.setSpacing(10)
        self._t_rtitle = QLabel(t("roster_title"))
        self._t_rtitle.setStyleSheet(serif_style(20, COLORS["ink"], 600))
        vv.addWidget(self._t_rtitle)
        self._t_rhint = QLabel(t("roster_hint"))
        hint = self._t_rhint
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:12px;")
        vv.addWidget(hint)
        self.roster_list = QLabel("")
        self.roster_list.setWordWrap(True)
        self.roster_list.setStyleSheet(
            f"color:{COLORS['ink']}; font-size:13px; background:{COLORS['paper_deep']};"
            f"border:1px solid {COLORS['line']}; border-radius:8px; padding:10px;")
        vv.addWidget(self.roster_list)

        rbtn = QHBoxLayout()
        self.btn_edit_roster = make_button(t("edit_roster"), "primary", min_height=44)
        self.btn_edit_roster.clicked.connect(self._edit_roster)
        rbtn.addWidget(self.btn_edit_roster)
        rbtn.addStretch(1)
        vv.addLayout(rbtn)
        lay.addWidget(self.roster_card)

        self.anti_card = PaperCard()
        card2 = self.anti_card
        v2 = QVBoxLayout(card2)
        v2.setContentsMargins(20, 16, 20, 16)
        v2.setSpacing(10)
        self._t_anti_title = QLabel(t("anti_title"))
        self._t_anti_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))
        v2.addWidget(self._t_anti_title)
        from PySide6.QtWidgets import QSpinBox as _SB
        # Material 开关 + 说明
        self.sw_anti_label = QLabel(t("anti_label"))
        self.sw_anti_label.setWordWrap(True)
        self.sw_anti_label.setStyleSheet(f"color:{COLORS['ink']}; font-size:14px; background:transparent;")
        self.chk_anti = SwitchControl(True)     # 接口与 QCheckBox 对齐：isChecked/setChecked/toggled
        self.spin_anti = _SB()
        self.spin_anti.setRange(app_data.ANTI_DUP_MIN_HOURS, app_data.ANTI_DUP_MAX_HOURS)
        self.spin_anti.setSuffix(" " + t("unit_hours"))
        self.spin_anti.setMinimumHeight(44)
        self.spin_anti.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.sw_anti_label, 1)
        row.addWidget(self.spin_anti)
        row.addSpacing(10)
        row.addWidget(self.chk_anti)
        v2.addLayout(row)
        re_row = QHBoxLayout()
        self.btn_reconfig = make_button(t("reconfig_btn"), "ghost", min_height=44)
        self.btn_reconfig.clicked.connect(lambda: self.on_reconfigure and self.on_reconfigure())
        re_row.addWidget(self.btn_reconfig)
        re_row.addStretch(1)
        v2.addLayout(re_row)

        self.chk_anti.toggled.connect(self._on_anti_toggle)
        self.spin_anti.valueChanged.connect(self._on_anti_change)
        lay.addWidget(card2)
        lay.addStretch(1)

        # 背景装饰色块（视差用；置于卡片下层，仅装饰）
        self._revealed: set = set()
        self._blobs: list = []
        self._blob_bases: list = []
        self._make_blobs(inner)

        scroll.setWidget(inner)
        scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        inner.installEventFilter(self)
        outer.addWidget(scroll, 1)

    # ---- 背景有机色块（倾斜椭圆 / 圆角矩形，莫兰迪低透明） ----
    def _make_blobs(self, inner: QWidget):
        self._blobs = [
            _Blob(COLORS["blue_soft"], 66, 360, 300, -8, "ellipse", inner),
            _Blob(COLORS["camel_soft"], 80, 210, 260, 13, "round", inner),
            _Blob(COLORS["green_soft"], 60, 200, 200, 24, "ellipse", inner),
        ]
        for b in self._blobs:
            b.lower()
        self._blob_bases = [(0, 340), (0, 850), (0, 1250)]

    def _place_blobs(self):
        """按滚动内容宽度摆放色块（右缘对齐、不对称）。"""
        if not self._blobs:
            return
        w = max(sc_w := self.inner.width(), 900)
        self._blob_bases = [(w - 470, 320), (w - 330, 760), (w - 250, 1180)]
        self._on_scroll()

    def _on_scroll(self):
        if not getattr(self, "_blobs", None):
            return
        v = self.scroll.verticalScrollBar().value() * 0.45   # 视差：比内容慢
        for blob, (bx, by) in zip(self._blobs, self._blob_bases):
            blob.move(int(bx), int(by - v))
        self._reveal_check()

    def _reveal_check(self):
        """内容区块滚入视口时轻量渐现上移（一次）。"""
        if not self.store:
            return
        vp = self.scroll.viewport()
        targets = [self.cfg_card, self.roster_card, self.anti_card]
        for i, card in enumerate(targets):
            if id(card) in self._revealed or not card.isVisible():
                continue
            y = card.mapTo(vp, QPoint(0, 0)).y()
            if y < vp.height() * 0.94:
                self._revealed.add(id(card))
                fade_slide_in(card, dx=0, dy=26, dur=520, delay=60 + i * 90)   # 渐现上移

    def eventFilter(self, obj, event):
        if obj is self.inner and event.type() == event.Type.Resize:
            QTimer.singleShot(0, self._place_blobs)
        return super().eventFilter(obj, event)

    # 配置项：轮次渲染
    ROWS = [
        ("row_name", "name"), ("row_mode", "mode"), ("row_total", "total"),
        ("row_all", "all"), ("row_pool", "pool"),
        ("row_long", "long"), ("row_short", "short"),
        ("row_anti", "anti"), ("row_path", "path"),
    ]

    def set_store(self, store: ClassStore, cfg: dict):
        self.store = store
        self.cfg = cfg
        self._revealed = set()
        self.refresh()
        QTimer.singleShot(0, self._place_blobs)
        self._reveal_check()

    def _fmt_list(self, nums: list[int], name_of) -> str:
        if not nums:
            return t("none_list")
        parts = []
        for n in sorted(nums)[:20]:
            nm = name_of(n)
            parts.append(f"{n:02d}{' ' + nm if nm else ''}")
        more = " …" if len(nums) > 20 else ""
        return "，".join(parts) + more

    def refresh(self):
        if not self.store:
            return
        cfg = self.cfg
        # 清空重建（保证顺序与刷新一致）
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        students = self.store.get_students(cfg)
        name_of = {s["num"]: s.get("name", "") for s in students}
        long_n = self.store.long_exempt()
        short_n = self.store.short_exempt()
        cool_n = self.store.cooling_nums(cfg)
        pool = [s for s in students if s["num"] not in set(long_n) and
                s["num"] not in set(short_n) and s["num"] not in set(cool_n)]

        def val(key):
            if key == "name":
                return cfg.get("name", self.store.name)
            if key == "mode":
                return t("mode_advanced") if cfg.get("mode") == MODE_ADVANCED else t("mode_simple")
            if key == "total":
                return t("unit_person", n=cfg.get("total_count", 0))
            if key == "all":
                return t("unit_person", n=len(students))
            if key == "pool":
                return t("pool_detail", n=len(pool), long=len(long_n),
                         short=len(short_n), cool=len(cool_n))
            if key == "long":
                return self._fmt_list(long_n, lambda n: name_of.get(n, ""))
            if key == "short":
                return self._fmt_list(short_n, lambda n: name_of.get(n, ""))
            if key == "anti":
                if cfg.get("anti_dup_enabled", True):
                    return t("anti_on_fmt", n=cfg.get("anti_dup_hours", 24))
                return t("anti_off")
            if key == "path":
                return str(self.store.dir)
            return ""

        for i, (label_key, key) in enumerate(self.ROWS):
            l = QLabel(t(label_key))
            l.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:13px;")
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            r = QLabel(val(key))
            r.setStyleSheet(f"color:{COLORS['ink']}; font-size:13px;")
            r.setWordWrap(True)
            r.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(l, i, 0)
            self.grid.addWidget(r, i, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(1, 320)

        # 名单预览
        names = self.store.roster_read()
        advanced = cfg.get("mode") == MODE_ADVANCED
        self.roster_card.setVisible(advanced)
        if advanced:
            shown = "，".join(f"{i+1}. {n}" for i, n in enumerate(names))
            self.roster_list.setText(shown if names else t("roster_empty"))
        # 防重控件状态
        self.chk_anti.setChecked(bool(cfg.get("anti_dup_enabled", True)), animate=False)
        self.spin_anti.setValue(int(cfg.get("anti_dup_hours", 24)))
        self.spin_anti.setEnabled(bool(cfg.get("anti_dup_enabled", True)))
        # 切到本页（或数据刷新）时，检查滚入视口的渐现
        QTimer.singleShot(0, self._reveal_check)

    # 防重设置即时保存
    def _on_anti_toggle(self, checked: bool):
        if not self.store:
            return
        self.spin_anti.setEnabled(checked)
        cfg = self.store.load_config()
        cfg["anti_dup_enabled"] = checked
        self.store.save_config(cfg)
        self.cfg = cfg
        self.refresh()
        self.settings_changed.emit()      # 联动：首页摇号池/提示立即更新

    def _on_anti_change(self, v: int):
        if not self.store:
            return
        cfg = self.store.load_config()
        cfg["anti_dup_hours"] = v
        self.store.save_config(cfg)
        self.cfg = cfg
        self.settings_changed.emit()

    def retranslate(self):
        self._t_title.setText(t("config_title"))
        self._t_rtitle.setText(t("roster_title"))
        self._t_rhint.setText(t("roster_hint"))
        self._t_anti_title.setText(t("anti_title"))
        self.sw_anti_label.setText(t("anti_label"))
        self.btn_edit_roster.setText(t("edit_roster"))
        self.btn_reconfig.setText(t("reconfig_btn"))
        self.refresh()

    def _edit_roster(self):
        if not self.store:
            return
        from .ui_dialogs import RosterEditorDialog
        dlg = RosterEditorDialog(self, self.store)
        if dlg.exec():
            cfg = self.store.load_config()
            self.cfg = cfg
            self.refresh()


# ===========================================================================
# 屏蔽管理页
# ===========================================================================

class ShieldPage(QWidget):
    """长期/短期屏蔽管理：全部学生列表 + 状态标注 + 批量添加/移除。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 10)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self._t_title = QLabel(t("shield_title"))
        self._t_title.setStyleSheet(serif_style(20, COLORS["ink"], 600))
        head.addWidget(self._t_title)
        head.addStretch(1)
        lay.addLayout(head)

        self._t_tip = QLabel(t("shield_hint"))
        tip = self._t_tip
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:12px;")
        lay.addWidget(tip)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([t("col_status"), t("col_num"), t("col_name"), t("col_note")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)  # 已有序号列
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        enable_touch_scroll(self.table)
        lay.addWidget(self.table, 1)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.btn_add_long = make_button(t("add_long"), "", min_height=44)
        self.btn_rm_long = make_button(t("rm_long"), "ghost", min_height=44)
        self.btn_add_short = make_button(t("add_short"), "", min_height=44)
        self.btn_rm_short = make_button(t("rm_short"), "ghost", min_height=44)
        bar.addWidget(self.btn_add_long)
        bar.addWidget(self.btn_rm_long)
        bar.addStretch(1)
        bar.addWidget(self.btn_add_short)
        bar.addWidget(self.btn_rm_short)
        lay.addLayout(bar)

        bar2 = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color:{COLORS['ink_soft']}; font-size:13px;")
        self.btn_clear_long = make_button(t("clear_long"), "danger", min_height=44)
        self.btn_clear_short = make_button(t("clear_short"), "danger", min_height=44)
        bar2.addWidget(self.summary)
        bar2.addStretch(1)
        bar2.addWidget(self.btn_clear_long)
        bar2.addWidget(self.btn_clear_short)
        lay.addLayout(bar2)

        self.btn_add_long.clicked.connect(lambda: self._pick("long", add=True))
        self.btn_add_short.clicked.connect(lambda: self._pick("short", add=True))
        self.btn_rm_long.clicked.connect(lambda: self._toggle_selected("long", add=False))
        self.btn_rm_short.clicked.connect(lambda: self._toggle_selected("short", add=False))
        self.btn_clear_long.clicked.connect(lambda: self._clear("long"))
        self.btn_clear_short.clicked.connect(lambda: self._clear("short"))

    def set_store(self, store: ClassStore, cfg: dict):
        self.store = store
        self.cfg = cfg
        self.refresh()
        fade_slide_in(self.table, dx=18, dy=0, dur=300, delay=80)

    def retranslate(self):
        self._t_title.setText(t("shield_title"))
        self._t_tip.setText(t("shield_hint"))
        self.table.setHorizontalHeaderLabels(
            [t("col_status"), t("col_num"), t("col_name"), t("col_note")])
        self.btn_add_long.setText(t("add_long"))
        self.btn_rm_long.setText(t("rm_long"))
        self.btn_add_short.setText(t("add_short"))
        self.btn_rm_short.setText(t("rm_short"))
        self.btn_clear_long.setText(t("clear_long"))
        self.btn_clear_short.setText(t("clear_short"))
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        students = self.store.get_students(self.cfg)
        long_n = set(self.store.long_exempt())
        short_n = set(self.store.short_exempt())
        self.table.setRowCount(0)
        self.table.setRowCount(len(students))
        for i, s in enumerate(students):
            num, name = s["num"], s.get("name", "")
            if num in long_n:
                status = t("status_long")
            elif num in short_n:
                status = t("status_short")
            else:
                status = t("status_normal")
            c0 = QTableWidgetItem(status)
            c0.setTextAlignment(Qt.AlignCenter)
            if num in long_n:
                c0.setBackground(QColor("#F2E0DF"))
            elif num in short_n:
                c0.setBackground(QColor("#E3E8DF"))
            else:
                c0.setBackground(QColor(COLORS["paper_deep"]))
            c1 = QTableWidgetItem(f"{num:02d}")
            c1.setTextAlignment(Qt.AlignCenter)
            c2 = QTableWidgetItem(name or t("unnamed"))
            if num in long_n:
                c2.setForeground(QColor(COLORS["pink_dark"]))
            c3 = QTableWidgetItem(t("note_never") if num in long_n else
                                  (t("note_today") if num in short_n else ""))
            self.table.setItem(i, 0, c0)
            self.table.setItem(i, 1, c1)
            self.table.setItem(i, 2, c2)
            self.table.setItem(i, 3, c3)
        self.summary.setText(t("shield_summary", total=len(students), long=len(long_n), short=len(short_n)))

    def _selected_nums(self) -> list[int]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        out = []
        for r in rows:
            it = self.table.item(r, 1)
            if it:
                out.append(int(it.text()))
        return out

    def _pick(self, kind: str, add: bool):
        """打开多选对话框加人。"""
        if not self.store:
            return
        students = self.store.get_students(self.cfg)
        cur = set(self.store.long_exempt() if kind == "long" else self.store.short_exempt())
        from .ui_dialogs import StudentPickDialog
        title = t("pick_title_pre") if kind == "long" else t("pick_title_short")
        dlg = StudentPickDialog(self, title, students, cur)
        if dlg.exec():
            selected = dlg.selected()
            if kind == "long":
                self.store.set_long_exempt(sorted(selected))
            else:
                self.store.set_short_exempt(sorted(selected))
            self.refresh()

    def _toggle_selected(self, kind: str, add: bool):
        if not self.store:
            return
        nums = self._selected_nums()
        if not nums:
            snack(self, t("snack_select_first"))
            return
        if kind == "long":
            cur = set(self.store.long_exempt())
            if add:
                cur.update(nums)
            else:
                cur.difference_update(nums)
            self.store.set_long_exempt(sorted(cur))
        else:
            cur = set(self.store.short_exempt())
            if add:
                cur.update(nums)
            else:
                cur.difference_update(nums)
            self.store.set_short_exempt(sorted(cur))
        self.refresh()

    def _clear(self, kind: str):
        if not self.store:
            return
        title = t("clear_long_title") if kind == "long" else t("clear_short_title")
        text = t("clear_long_fmt") if kind == "long" else t("clear_short_fmt")
        if not ask(self, title, text, yes=t("dlg_reset"), no=t("dlg_cancel")):
            return
        if kind == "long":
            self.store.set_long_exempt([])
        else:
            self.store.set_short_exempt([])
        self.refresh()
