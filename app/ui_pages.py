# -*- coding: utf-8 -*-
"""
页面层 v2「朱墨」：
- 抽号页：编辑式版面（细线分区，无卡片堆叠），滚轮数字 + 落章定格，
  批量抽号纸票盖章，池空自动重置横幅；
- 记录页：管理员密码 → 按时间段归档删除；
- 统计 / 配置 / 屏蔽：同一套排版语言（大字标题 + 细线行）。
响应式：>=900 双栏，<900 单栏可滚动；高度不足时自动缩小大数字。
"""

from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import (Qt, QTimer, QRectF, QPoint, QPointF, Signal, QSize,
                            Property, QVariantAnimation, QPropertyAnimation,
                            QEasingCurve)
from PySide6.QtGui import (QColor, QMouseEvent, QPainter, QFont, QPen, QBrush,
                           QLinearGradient, QRadialGradient)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
                               QScrollArea, QGridLayout, QFrame,
                               QAbstractItemView, QHeaderView, QSizePolicy, QSpacerItem)

from . import app_data
from .motion import (pop_in as m_pop_in, bounce as m_bounce,
                     stagger as m_stagger,
                     animate as m_animate)
from .app_data import ClassStore, MODE_ADVANCED, MODE_SIMPLE
from .lang import t
from .theme import (COLORS, serif_style, MOTION, display_font,
                    emphasized_decelerate, type_style)
from .ui_widgets import (RollLabel, SealMark, StampRing, Halo, Badge,
                         start_halo, stop_halo, flash_halo, make_button, ask, inform,
                         fade_in, fade_slide_in, snack, SwitchControl, NumberStepper, ChoiceChip,
                         Banner, BatchRevealOverlay, enable_touch_scroll,
                         flash_item_background, hairline, PaperCard,
                         glow_pixmap, IconGlyph, PctBarDelegate, WrapLabel)


def _page_kicker(num: str) -> QLabel:
    """杂志式章节号：小字、大字距、accent 色。"""
    lab = QLabel(num)
    lab.setStyleSheet(
        f"color:{COLORS['accent']}; font-size:12px; font-weight:600;"
        "letter-spacing:2px; background:transparent;")
    return lab


def _section_title(text: str) -> QWidget:
    """M3 区块标题：title large + 600 字重，不加装饰线。"""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    lab = QLabel(text)
    lab.setStyleSheet(
        f"color:{COLORS['on_surface']}; font-size:21px; font-weight:600;"
        "background:transparent;")
    v.addWidget(lab)
    return w


def _soft_gap(n: int) -> QSpacerItem:
    """可压缩的垂直间隙：空间充足时为 n，不足时可压到 0（防小窗元素互相重叠）。"""
    return QSpacerItem(0, n, QSizePolicy.Minimum, QSizePolicy.Maximum)


class ResultStage(QWidget):
    """抽号舞台：干净留白，数字与姓名直接落在卡片上；不再画圆盘/光晕。

    落定光环直接画在本控件里（fire_halo）：旧实现用 BurstOverlay 半透明
    子窗覆盖在窗口上，会强制整窗走 alpha 合成，定格瞬间整窗反复重绘——
    实测出现单帧 173ms 冻结；改为舞台自身 paintEvent 画扩散环后，只重绘
    舞台区域，整窗不再被拖累。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wm = True
        self._running = False
        self._halo = 0.0            # 光环进度 0→1（0 = 关闭）
        self._halo_color = QColor(COLORS["primary"])
        self._halo_max_r = 190.0

    def set_watermark(self, on: bool):
        self._wm = bool(on)

    def set_running(self, on: bool):
        self._running = bool(on)

    def disc_rect(self) -> QRectF:
        # 兼容旧调用（光晕/光环已移除）
        return QRectF(self.rect())

    # ---- 落定光环（舞台内绘制，不产生额外窗口层） ----
    def get_halo(self):
        return self._halo

    def set_halo(self, v):
        self._halo = float(v)
        self.update()

    halo = Property(float, get_halo, set_halo)

    def fire_halo(self, color: str, max_r: float = 190, dur: int = 760):
        """从舞台中心扩散两圈主色光环，透明度回收后自动关闭。"""
        self._halo_color = QColor(color)
        self._halo_max_r = float(max_r)
        a = getattr(self, "_halo_anim", None)
        if a is not None:
            try:
                a.stop()
            except Exception:
                pass
        anim = QPropertyAnimation(self, b"halo", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(max(120, int(dur)))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(self._halo_done)
        anim.start()
        self._halo_anim = anim

    def _halo_done(self):
        self._halo = 0.0
        self.update()

    def paintEvent(self, event):
        if self._halo <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        base = min(self.width(), self.height()) * 0.16
        t = max(0.0, min(1.0, self._halo))
        # ① 中心闪光：落定瞬间一下打亮，200ms 内迅速收掉（冲击感来源）
        flash = max(0.0, 1.0 - t / 0.34)
        if flash > 0.01:
            r = min(self.width(), self.height()) * (0.30 + 0.22 * t)
            g = QRadialGradient(c, r)
            col = QColor(self._halo_color)
            a = col.alphaF()
            col.setAlphaF(a * 0.20 * flash ** 1.6)
            g.setColorAt(0.0, col)
            col2 = QColor(self._halo_color)
            col2.setAlphaF(0.0)
            g.setColorAt(1.0, col2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, r, r)
        # ② 两圈错开扩散，快衰慢散
        for delay, strength, width in ((0.0, 1.0, 7.0), (0.16, 0.55, 2.4)):
            k = (t - delay) / (1.0 - delay)
            if k <= 0:
                continue
            k = min(1.0, k)
            r = base + k * (self._halo_max_r - base)
            col = QColor(self._halo_color)
            col.setAlphaF(max(0.0, 0.36 * strength * (1.0 - k) ** 1.5))
            p.setPen(QPen(col, max(1.0, width * (1.0 - k))))
            p.setBrush(QBrush())
            p.drawEllipse(c, r, r)
        p.end()


# ===========================================================================
# 抽号页
# ===========================================================================

class DrawPage(QWidget):
    TICK_MS = 38
    ROW_H = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self._pool: list[dict] = []
        self._snap: dict = {}
        self._running = False
        self._num_px = 0
        self._prev_round_len = 0
        self._wide = None
        self._batch_overlay = None
        self._result: dict | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        root.addWidget(self.scroll)
        # 主滚动区也要支持触控拖拽（小窗内容超出视口时可滚到底）
        enable_touch_scroll(self.scroll)

        self.content = QWidget()
        self.content.setStyleSheet(f"background:{COLORS['surface']};")
        self.grid = QGridLayout(self.content)
        # 四边留白取同一值：左 28 / 右 24 / 上 22 / 下 18 的旧值会让
        # 卡片组看起来微微偏右偏上，肉眼说不出哪里错但就是不齐。
        self.grid.setContentsMargins(24, 20, 24, 20)
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(20)
        self.scroll.setWidget(self.content)

        # ---------------- 主区：elevated 卡片 ----------------
        # 卡片不再内缩画阴影：可见轮廓 = 控件 rect，与下方批量卡、右栏严格对齐。
        self.hero = PaperCard(self.content, radius=28, variant="elevated")
        from PySide6.QtWidgets import QSizePolicy
        self.hero.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        hv = QVBoxLayout(self.hero)
        # 卡内留白：24 / 16 / 24 / 20（原先靠 16px 阴影环带撑出来的视觉留白）
        hv.setContentsMargins(24, 16, 24, 20)
        hv.setSpacing(8)
        self.hero_lay = hv

        self.banner = Banner(self, "", "")
        hv.addWidget(self.banner)

        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 14, 0)
        self.counter = QLabel("")
        self.counter.setFixedHeight(28)
        self.counter.setStyleSheet(
            f"color:{COLORS['on_surface_variant']}; font-size:12px;"
            f" background:{COLORS['surface_container_high']}; border-radius:10px;"
            " padding:0 10px;")
        self.seal = SealMark("中", self.hero)
        top.addWidget(self.counter)
        top.addStretch(1)
        top.addWidget(self.seal)
        hv.addLayout(top)

        self.result = ResultStage()
        self.result.set_watermark(True)
        self.result.setCursor(Qt.PointingHandCursor)
        self.result.mousePressEvent = self._on_card_press
        rv = QVBoxLayout(self.result)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(2)
        rv.addStretch(1)

        self.halo = None
        self.stamp_ring = None

        self.empty_icon = IconGlyph("dice", 64, COLORS["outline_variant"],
                                    width=2.0)
        rv.addWidget(self.empty_icon, 0, Qt.AlignHCenter)
        rv.addSpacerItem(_soft_gap(14))

        self.caption = QLabel("")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setStyleSheet(
            f"color:{COLORS['outline']}; font-size:12px; letter-spacing:2px;"
            "background:transparent;")
        rv.addWidget(self.caption, 0, Qt.AlignHCenter)
        rv.addSpacerItem(_soft_gap(10))

        self.num_label = RollLabel("", self.result)
        self.num_label.set_pixel_size(150, 600)
        # 水平方向忽略 sizeHint：大号时 sizeHint 会把网格列撑爆（小窗右缘溢出）
        self.num_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        rv.addWidget(self.num_label, 0, Qt.AlignHCenter)
        rv.addSpacerItem(_soft_gap(6))

        self.name_label = QLabel("")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:23px; font-weight:500;"
            "letter-spacing:2px; background:transparent;")
        rv.addWidget(self.name_label, 0, Qt.AlignHCenter)

        self.hint_label = QLabel("")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet(
            f"color:{COLORS['outline']}; font-size:12px; background:transparent;")
        rv.addSpacerItem(_soft_gap(18))
        rv.addWidget(self.hint_label, 0, Qt.AlignHCenter)
        rv.addStretch(1)

        hv.addWidget(self.result, 1)

        # 主操作按钮（hero 卡片内）
        ctl = QHBoxLayout()
        ctl.setContentsMargins(0, 6, 0, 4)
        ctl.setSpacing(10)
        self.btn_toggle = make_button(t("draw_start"), "filled", min_height=52)
        self.btn_toggle.setFixedHeight(52)
        self.btn_toggle.setMinimumWidth(220)
        self.btn_toggle.clicked.connect(self.toggle)
        # 点击反馈：按钮自身水波纹 + 弹性脉冲。
        # 不再叠 BurstOverlay 半透明浮层——那会强制整窗 alpha 合成，
        # 每次点击都让整窗重绘（定格/连点时卡顿的来源之一）。
        self.btn_toggle.clicked.connect(lambda: m_bounce(self.btn_toggle, s=0.90, dur=380))
        self.btn_reset = make_button(t("draw_reset_round"), "outlined", min_height=42)
        self.btn_reset.setMinimumWidth(110)
        self.btn_reset.clicked.connect(self._reset_round)
        self.btn_export = make_button(t("draw_export"), "outlined", min_height=42)
        self.btn_export.setMinimumWidth(110)
        self.btn_export.clicked.connect(self._export)
        ctl.addStretch(1)
        ctl.addWidget(self.btn_toggle)
        ctl.addSpacing(8)
        ctl.addWidget(self.btn_reset)
        ctl.addWidget(self.btn_export)
        ctl.addStretch(1)
        hv.addLayout(ctl)

        # ---------------- 批量卡片 ----------------
        self.batch_card = PaperCard(self.content, radius=24, variant="elevated")
        bh = QHBoxLayout(self.batch_card)
        bh.setContentsMargins(18, 10, 14, 10)
        bh.setSpacing(8)
        self.batch_kicker = QLabel(t("batch_title"))
        self.batch_kicker.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:14px; font-weight:600;"
            "background:transparent;")
        self.stepper = NumberStepper(app_data.BATCH_DEFAULT, 1, app_data.BATCH_MAX)
        self.stepper.valueChanged.connect(self._on_batch_value)
        self.chips = {}
        for n in (3, 5, 10):
            c = ChoiceChip(t("batch_count_unit", n=n), False, self.batch_card)
            c.clicked.connect(lambda _=False, v=n, chip=c: (self.stepper.setValue(v),
                                                            chip.setChecked(True)))
            self.chips[n] = c
        self.btn_batch = make_button(t("batch_draw_n", n=app_data.BATCH_DEFAULT), "tonal", 48)
        self.btn_batch.setMinimumWidth(140)
        self.btn_batch.clicked.connect(self.batch_draw)
        # 同上：只保留弹性脉冲，浮层光环去掉（避免整窗 alpha 合成）
        self.btn_batch.clicked.connect(lambda: m_bounce(self.btn_batch, s=0.90, dur=380))

        bh.addWidget(self.batch_kicker)
        bh.addSpacing(6)
        bh.addWidget(self.stepper)
        bh.addSpacing(4)
        for n in (3, 5, 10):
            bh.addWidget(self.chips[n])
        bh.addStretch(1)
        bh.addWidget(self.btn_batch)

        # ---------------- 右栏 ----------------
        self.rail = PaperCard(self.content, radius=24, variant="elevated")
        from PySide6.QtWidgets import QSizePolicy as _SP
        self.rail.setSizePolicy(_SP.Preferred, _SP.Expanding)
        rl = QVBoxLayout(self.rail)
        rl.setContentsMargins(22, 18, 20, 14)
        rl.setSpacing(8)

        h1 = QHBoxLayout()
        self.t_round = QLabel(t("round_title"))
        self.t_round.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:14px; font-weight:600;"
            "background:transparent;")
        self.round_count = QLabel("00")
        self.round_count.setStyleSheet(
            f"color:{COLORS['primary']}; font-size:20px; font-weight:600;"
            "background:transparent;")
        h1.addWidget(self.t_round)
        h1.addStretch(1)
        h1.addWidget(self.round_count)
        rl.addLayout(h1)

        self.round_list = QListWidget()
        self.round_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.round_list.setFocusPolicy(Qt.NoFocus)
        self.round_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # 常显滚动条：池子/本轮列表的内容宽度与滚动条出现与否绑定，
        # 抽完一个名字后滚动条消失会让整列条目横向"跳"一下（宽度突变）。
        self.round_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        enable_touch_scroll(self.round_list)
        rl.addWidget(self.round_list, 0)
        self.round_empty = QLabel(t("round_empty"))
        self.round_empty.setStyleSheet(
            f"color:{COLORS['outline']}; font-size:12px; padding:10px 0;"
            "background:transparent;")
        rl.addWidget(self.round_empty)

        rl.addSpacing(12)
        rl.addWidget(hairline())

        h2 = QHBoxLayout()
        self.t_pool = QLabel(t("pool_title"))
        self.t_pool.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:14px; font-weight:600;"
            "background:transparent;")
        h2.addWidget(self.t_pool)
        h2.addStretch(1)
        rl.addLayout(h2)

        self.pool_stats = QLabel("")
        self.pool_stats.setTextFormat(Qt.RichText)
        self.pool_stats.setStyleSheet(
            f"color:{COLORS['on_surface_variant']}; font-size:11.5px;"
            "background:transparent;")
        rl.addWidget(self.pool_stats)

        self.pool_list = QListWidget()
        self.pool_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.pool_list.setFocusPolicy(Qt.NoFocus)
        self.pool_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # 同上：避免"抽完一个 → 条目变少 → 滚动条消失 → 整列横向跳"
        self.pool_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        enable_touch_scroll(self.pool_list)
        rl.addWidget(self.pool_list, 4)

        self._on_batch_value(self.stepper.value())
        self.grid.addWidget(self.hero, 0, 0)
        self.grid.addWidget(self.batch_card, 2, 0)
        self.grid.addWidget(self.rail, 0, 1, 2, 1)
        self.grid.setColumnStretch(0, 3)
        self.grid.setColumnStretch(1, 2)
        self.grid.setRowStretch(0, 1)
        self.grid.setRowStretch(1, 0)
        
        self.result.installEventFilter(self)
        self.content.installEventFilter(self)

    # ------------------------------------------------------------- 数据
    def set_store(self, store: ClassStore, cfg: dict):
        self.stop_silent()
        self.store = store
        self.cfg = cfg
        self._prev_round_len = 0
        self._result = None
        self.banner.hide()
        self.seal.hide()
        self.num_label.set_now("")
        self.name_label.setText("")
        self._set_state("empty")
        self.refresh()

    def play_entrance(self):
        """兼容旧调用：入场动画统一由 MainWindow.page_enter 负责。

        以前这里会对 hero / rail 各自做一次带 20/80ms 延迟的淡入，而整页
        同时还有一次 page_enter —— 两套动画叠在同一批控件上，延迟那段还会
        先把卡片全亮画一帧再跳回透明，观感就是「闪一下再糊上来」。
        现在只保留整页一个动作，这里留空实现避免外部旧调用报错。
        """

    def refresh(self):
        if self.store is None:
            return
        self._snap = self.store.pool_snapshot(self.cfg)
        self._pool = self._snap["pool"]
        self._refresh_round(full=True)
        self._refresh_pool()
        self._refresh_hint()
        self._sync_batch()
        self._refresh_counter()
        self._restore_last()

    def _restore_last(self):
        """重新打开软件时，舞台上显示上一轮最后抽中的结果，而不是一片空白。"""
        if self._running or not self.store:
            return
        items = self.store.round_list()
        if not items:
            self._set_state("empty")
            return
        last = items[-1]
        try:
            num = int(last.get("num", 0))
        except (TypeError, ValueError):
            return
        self.num_label.set_now(f"{num:02d}" if num < 100 else str(num))
        self.num_label.set_text_color(COLORS["accent"])
        self._set_state("result")
        self.name_label.setText(last.get("name", "") or "")
        self.result.set_watermark(False)

    def _hero_pulse(self):
        """落定时数字区域轻微缩放脉冲（用 _pop 属性，不动 geometry）。"""
        self.num_label.pop_once(380)

    def _reveal_name(self, name: str):
        if not name:
            self._set_name("")
            return
        self._set_name(name)
        self.name_label.show()
        try:
            m_pop_in(self.name_label, dy=16, s=0.88, dur=520)  # 姓名弹性揭晓
        except Exception:
            pass

    def _set_name(self, text: str, muted: bool = False):
        self.name_label.setText(text)
        color = COLORS["outline"] if muted else COLORS["on_surface"]
        self.name_label.setStyleSheet(
            f"color:{color}; font-size:23px; font-weight:500;"
            "letter-spacing:2px; background:transparent;")

    def _set_state(self, mode: str):
        """舞台三态：empty 空、running 抽号中、result 已抽中。"""
        empty = mode == "empty"
        self.caption.setText(
            t("draw_empty_hint") if empty else
            (t("draw_running") if mode == "running" else t("draw_result")))
        self.num_label.setVisible(not empty)
        self.name_label.setVisible(not empty)
        self.empty_icon.setVisible(empty)
        color = {"running": COLORS["primary"], "result": COLORS["accent"],
                 "empty": COLORS["outline"]}[mode]
        self.caption.setStyleSheet(
            f"color:{color}; font-size:12px; letter-spacing:2px; background:transparent;")

    def _refresh_counter(self):
        n = len(self.store.round_list()) + 1 if self.store else 1
        self.counter.setText(t("round_counter_fmt", n=n))

    def _add_row(self, widget: QListWidget, text: str, num: int = -1, h: int = 40):
        item = QListWidgetItem(text)
        item.setSizeHint(QSize(0, h))
        if num >= 0:
            item.setData(Qt.UserRole, num)
        widget.addItem(item)
        return item

    def _refresh_round(self, full: bool = True):
        items = self.store.round_list() if self.store else []
        prev = getattr(self, "_prev_round_len", 0)
        self.round_list.clear()
        for i, it in enumerate(items):
            name = it.get("name") or f"#{int(it.get('num', 0)):02d}"
            num = int(it.get("num", 0))
            txt = f"{num:02d}    {name}" if name and not name.startswith("#") else name
            item = self._add_row(self.round_list, txt, num, 40)
            if full and i >= prev:
                flash_item_background(item, QColor(COLORS["primary_container"]), dur=800)
        self._prev_round_len = len(items)
        self.round_count.setText(f"{len(items):02d}")
        # 右栏不让两条记录撑出大半屏空白：按内容限高，剩余空间给摇号池
        self.round_list.setMaximumHeight(max(40, min(420, len(items) * 44 + 10)))
        self.round_list.setVisible(bool(items))
        self.round_empty.setVisible(not items)

    def _append_round_row(self, stu: dict):
        idx = self.round_list.count()
        num = int(stu.get("num", 0))
        name = stu.get("name") or f"#{num:02d}"
        item = self._add_row(self.round_list, f"{num:02d}    {name}", num, 40)
        self.round_list.scrollToBottom()
        flash_item_background(item, QColor(COLORS["primary_container"]), dur=800)
        self._prev_round_len = idx + 1
        self.round_count.setText(f"{idx + 1:02d}")
        # 第一次抽号时列表还处于隐藏状态，这里要显式打开，否则会一直显示「尚无记录」
        self.round_list.setVisible(True)
        self.round_empty.setVisible(False)
        self.round_list.setMaximumHeight(max(40, min(420, (idx + 1) * 44 + 10)))

    def _refresh_pool(self):
        if not self.store:
            return
        snap = self._snap or self.store.pool_snapshot(self.cfg)
        self._update_badges(snap)
        self.pool_list.clear()
        for s in snap["pool"]:
            name = s.get("name") or ""
            txt = f"{s['num']:02d}    {name if name else t('unnamed')}"
            self._add_row(self.pool_list, txt, s["num"], 36)

    def _update_badges(self, snap: dict | None = None):
        snap = snap or self._snap or {}
        long_n, short_n = len(snap.get("long", set())), len(snap.get("short", set()))
        dot = '<span style="color:{c}">●</span> '
        parts = [
            dot.format(c=COLORS["primary"]) + t("pool_ok", n=len(snap.get("pool", []))),
            dot.format(c=COLORS["error"]) + t("pool_block", n=long_n + short_n),
            dot.format(c=COLORS["outline"]) + t("pool_cool", n=len(snap.get("cool", set()))),
        ]
        self.pool_stats.setText("&nbsp;&nbsp;".join(parts))
        self.pool_stats.setToolTip(t("pool_block_tip", long=long_n, short=short_n))

    def _remove_pool_row(self, num: int):
        for i in range(self.pool_list.count()):
            item = self.pool_list.item(i)
            if item and item.data(Qt.UserRole) == num:
                self.pool_list.takeItem(i)
                return

    def _refresh_hint(self):
        total = self.cfg.get("total_count", 0)
        n_pool = len(self._pool)
        if total == 0:
            text = t("hint_no_config")
        elif n_pool == 0:
            text = t("hint_empty")
        else:
            extra = ""
            if not self.cfg.get("anti_dup_enabled", True):
                extra = t("hint_anti_off")
            elif self.cfg.get("mode") == MODE_ADVANCED:
                extra = t("hint_advanced")
            text = t("hint_pool", n=n_pool, extra=extra)
        self.hint_label.setText(text)

    def _sync_batch(self):
        n = max(1, len(self._pool))
        self.stepper.setMaximum(n)
        if self.stepper.value() > n:
            self.stepper.setValue(n)
        self.btn_batch.setEnabled(len(self._pool) > 0)
        self.btn_batch.setText(t("batch_draw_n", n=self.stepper.value()))

    def _on_batch_value(self, n: int):
        self.btn_batch.setText(t("batch_draw_n", n=n))
        for k, c in self.chips.items():
            c.setChecked(k == n)

    @staticmethod
    def _clamp_batch(want: int, pool_n: int) -> tuple[int, bool]:
        try:
            want = int(want)
        except (TypeError, ValueError):
            want = 1
        if pool_n <= 0:
            return 0, True
        if want > pool_n:
            return pool_n, True
        return max(1, want), False

    # --------------------------------------------------------- 抽号
    def _stretch_grid(self):
        """精确分配：hero 撑满扣除批量行与边距后的全部高度。"""
        if getattr(self, "_stretching", False):
            return
        self._stretching = True
        try:
            self._do_stretch()
        finally:
            self._stretching = False

    def _do_stretch(self):
        vp_h = self.scroll.viewport().height()
        if vp_h <= 0:
            return
        # 绝不再给 hero 设 maximumHeight 硬锁：小窗时内容（计数+结果+按钮行）
        # 塞不下固定高度就会溢出卡片，被 grid 下一行的批量卡片盖住——这正是
        # "大量元素被遮挡"的根因。改为只给下限，高度由内容驱动。
        self.hero.setMaximumHeight(16777215)

        m = self.grid.contentsMargins()
        vspace = self.grid.verticalSpacing()
        batch_h = 74
        if self._wide:
            # 宽屏：hero 与右栏左右并排，只有两行；hero 按视口剩余精确自适应，
            # 不设大下限——否则 need > 视口会把批量行底部切掉。数字字号会
            # 随 result 变小自动收敛，内容仍放得下。
            hero_h = max(280, vp_h - m.top() - m.bottom() - vspace - batch_h)
            self.rail.setMinimumHeight(0)
            self.rail.setMaximumHeight(16777215)
            need = m.top() + m.bottom() + vspace + hero_h + batch_h
            self.grid.setRowStretch(0, 1)
            self.grid.setRowStretch(1, 0)
            self.grid.setRowStretch(2, 0)
        else:
            # 窄屏：hero / 批量 / 右栏 三行堆叠。给每行足量高度，让 content
            # 撑到内容所需总高，由 QScrollArea 滚动承载（否则会溢出到 content
            # 之外被底部导航栏盖住，且滚不到）。
            # hero 按视口精确自适应：保证 hero + 批量行能完整落在视口内，
            # 否则批量行底部会被导航栏盖住（真实 exe 带标题栏，视口比
            # 预期小约 32px，写死 340 会挤出去）。右栏放下方由滚动承载。
            hero_h = max(280, min(460, vp_h - m.top() - m.bottom()
                                   - 2 * vspace - batch_h))
            rail_h = 360
            self.rail.setMinimumHeight(rail_h)
            self.rail.setMaximumHeight(16777215)
            need = m.top() + m.bottom() + hero_h + batch_h + rail_h + vspace * 2
            self.grid.setRowStretch(0, 1)
            self.grid.setRowStretch(1, 0)
            self.grid.setRowStretch(2, 0)

        self.content.setMinimumHeight(max(vp_h, need))
        self.hero.setMinimumHeight(hero_h)
        self.batch_card.setMinimumHeight(batch_h)

        # 布局生效后再按实际尺寸校准数字与文字字号
        lay = self.hero.layout()
        if lay is not None:
            lay.activate()
        self._apply_num_size(self._current_digits())
        self._scale_result_text()

    def _current_digits(self) -> int:
        txt = "".join(c for c in (self.num_label.text() or "") if c.isdigit())
        return len(txt) if txt else 2

    def _scale_result_text(self):
        """姓名/提示字号跟随卡片高度缩放（空态与结果态都要调用）。"""
        h = max(120, self.result.height())
        hint_px = max(11, min(22, int(h * 0.05)))
        self.hint_label.setStyleSheet(
            f"color:{COLORS['outline']}; font-size:{hint_px}px; background:transparent;")
        name_px = max(18, min(48, int(h * 0.12)))
        self.name_label.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:{name_px}px; font-weight:500;"
            "letter-spacing:2px; background:transparent;")

    def _scale_empty_state(self):
        """空态的骰子图标和文字跟随卡片尺寸缩放。"""
        h = max(120, self.result.height())
        icon_px = max(48, min(280, int(h * 0.38)))
        self.empty_icon.setFixedSize(icon_px, icon_px)
        font_px = max(13, min(32, int(h * 0.075)))
        cap_color = COLORS["primary"] if self.caption.text() and "抽" not in self.caption.text() else COLORS["outline"]
        self.caption.setStyleSheet(
            f"color:{cap_color}; font-size:{font_px}px; letter-spacing:2px; background:transparent;")
        self._scale_result_text()

    def _apply_num_size(self, digits: int):
        h = max(120, self.result.height())
        w = max(200, self.result.width())
        vp = max(240, self.scroll.viewport().height())
        # 视口上限：防止从大窗带过来的巨大字号把 hero 内容撑爆（小窗溢出）
        base = int(min(h * 0.44, w * 0.30, vp * 0.26))
        if digits == 3:
            base = int(base * 0.74)
        elif digits >= 4:
            base = int(base * 0.58)
        base = max(40, base)
        if base == self._num_px:
            return
        self._num_px = base
        self.num_label.set_pixel_size(base, 600)

    def toggle(self):
        if not self.store:
            return
        if self._running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.store:
            return
        snap = self.store.pool_snapshot(self.cfg)
        self._snap = snap
        self._pool = snap["pool"]
        if not self._pool:
            if not self._maybe_auto_reset(force=True):
                snack(self, t("snack_pool_empty"), kind="error", duration=3600)
            return
        self._running = True
        self._result = None
        self.seal.hide()
        self._set_name("· · ·", muted=True)
        self._set_state("running")
        self.num_label.set_text_color(COLORS["accent"])
        self.btn_toggle.setText(t("draw_stop"))
        self.num_label.set_rolling(True)
        self._num_px = 0
        self._apply_num_size(2)
        self._refresh_pool_size()
        self.result.set_running(True)
        self._timer.start()
        self._tick()

    def _refresh_pool_size(self):
        """抽号中把大数字容器撑到可用高度（避免布局跳动）。"""
        self.result.updateGeometry()

    def _tick(self):
        if not self._running or not self._pool:
            return
        s = random.choice(self._pool)
        num = s["num"]
        self.num_label.set_fast(f"{num:02d}" if num < 100 else str(num), 52)
        self._apply_num_size(len(str(num)))

    def stop(self):
        if not self._running:
            return
        self._timer.stop()
        self._running = False
        self.result.set_running(False)

        if not self._pool:
            self.refresh(); return
        result = random.choice(self._pool)
        self._result = result
        num, name = result["num"], result.get("name", "")
        anti = bool(self.cfg.get("anti_dup_enabled", True))
        self.store.record_draws([{"num": num, "name": name}],
                                self.cfg.get("mode", MODE_SIMPLE), anti_dup=anti)

        self._snap = self.store.pool_snapshot(self.cfg)
        self._pool = self._snap["pool"]
        self._append_round_row(result)
        self._remove_pool_row(num)
        self._update_badges()
        self._refresh_hint()
        self._sync_batch()

        QTimer.singleShot(90, lambda: self._rolling_step())
        QTimer.singleShot(200, lambda: self._rolling_step())
        QTimer.singleShot(330, lambda: self._settle(result))

        QTimer.singleShot(1250, lambda st=self.store: self._maybe_auto_reset(expect_store=st))

    def _rolling_step(self):
        if not self._pool:
            return
        s = random.choice(self._pool)
        self.num_label.set_fast(f"{s['num']:02d}" if s["num"] < 100 else str(s["num"]), 90)

    def _settle(self, result: dict):
        try:
            self._do_settle(result)
        except Exception:
            pass

    def _do_settle(self, result: dict):
        num, name = result["num"], result.get("name", "")
        self.btn_toggle.setText(t("draw_start"))
        self.num_label.set_rolling(False)
        self.num_label.roll_to(f"{num:02d}" if num < 100 else str(num), 380)
        self.num_label.set_text_color(COLORS["accent"])
        self._apply_num_size(len(str(num)))
        self._set_state("result")
        QTimer.singleShot(180, lambda: self._reveal_name(name))
        self.result.set_watermark(False)
        self.result.set_running(False)
        self.seal.stamp()
        # 数字落定瞬间：真正向外弹一下（MotionEffect 已允许出框）+ 中心闪光
        QTimer.singleShot(300, lambda: (
            m_bounce(self.num_label, s=1.14, dur=620, rot=-0.6),
            self.result.fire_halo(COLORS["primary"], max_r=210, dur=780),
            m_bounce(self.seal, s=1.10, dur=520)))
        # 池列表刷新推迟到弹跳峰值之后：避免 55 行重建与动画抢同一批帧
        QTimer.singleShot(960, self._refresh_pool)
        QTimer.singleShot(980, self._refresh_counter)

    # --------------------------------------------------------- 批量
    def batch_draw(self):
        if not self.store:
            return
        snap = self.store.pool_snapshot(self.cfg)
        self._snap = snap
        self._pool = snap["pool"]
        if not self._pool:
            if not self._maybe_auto_reset(force=True):
                inform(self, t("batch_title"), t("batch_none"), warn=True)
            return
        want = max(1, self.stepper.value())
        want, exceeded = self._clamp_batch(want, len(self._pool))
        if exceeded:
            if not ask(self, t("batch_exceed_title"),
                       t("batch_exceed_fmt", pool=len(self._pool), want=self.stepper.value()),
                       yes=t("batch_draw_n", n=len(self._pool)), no=t("dlg_cancel")):
                return
        picks = random.sample(self._pool, want)
        anti = bool(self.cfg.get("anti_dup_enabled", True))
        self.store.record_draws(picks, self.cfg.get("mode", MODE_SIMPLE), anti_dup=anti)

        self._snap = self.store.pool_snapshot(self.cfg)
        self._pool = self._snap["pool"]
        self._prev_round_len = max(0, len(self.store.round_list()) - want)
        self._refresh_round(full=True)
        self._refresh_pool()
        self._refresh_hint()
        self._sync_batch()
        self._refresh_counter()

        self.cfg["batch_count"] = want
        try:
            self.store.save_config(self.cfg, durable=False)
        except Exception:
            pass

        overlay = BatchRevealOverlay(self.window(), picks,
                                     [s["num"] for s in snap["pool"]])
        overlay.closed.connect(self._on_batch_closed)
        self._batch_store = self.store
        self._batch_overlay = overlay
        overlay.show(); overlay.raise_(); overlay.start()
        snack(self, t("batch_snack_fmt", n=len(picks)), kind="success", duration=2400)

    def _on_batch_closed(self):
        self._batch_overlay = None
        if not self._maybe_auto_reset(expect_store=getattr(self, "_batch_store", None)):
            self._restore_last()

    # --------------------------------------------------------- 自动重置
    def _maybe_auto_reset(self, force: bool = False, expect_store=None) -> bool:
        if not self.store:
            return False
        if expect_store is not None and expect_store is not self.store:
            return False
        snap = self.store.pool_snapshot(self.cfg)
        self._snap = snap
        self._pool = snap["pool"]
        if snap["pool"]:
            self._sync_batch()
            return False
        total = snap["total"]
        if total <= 0:
            return False
        if len(snap["long"] | snap["short"]) >= total:
            if force:
                inform(self, t("batch_title"), t("pool_blocked_all"), warn=True)
            return False
        n = len(self.store.round_list())
        self.store.reset_round()
        self.refresh()
        self.num_label.set_text_color(COLORS["on_surface"])
        self._show_reset_banner(n)
        snack(self, t("auto_reset_snack"), kind="success", duration=3400)
        return True

    def _show_reset_banner(self, n: int):
        old = getattr(self, "banner", None)
        if old is not None:
            self.hero_lay.removeWidget(old)
            old.hide(); old.deleteLater()
        self.banner = Banner(self, t("auto_reset_title"),
                             t("auto_reset_fmt", n=n) if n else t("auto_reset_hint"),
                             kind="success")
        self.hero_lay.insertWidget(0, self.banner)
        self.banner.pop(4600)

    # -------------------------------------------------------- 其他
    def stop_silent(self):
        self.num_label.set_rolling(False)
        if self._running:
            self._timer.stop()
            self._running = False
            self.result.set_running(False)

    def _on_card_press(self, ev: QMouseEvent):
        if self._running:
            self.stop()
        else:
            self.toggle()

    def eventFilter(self, obj, event):
        if obj in (self.content, self.scroll) and event.type() == event.Type.Resize:
            if not getattr(self, "_stretching", False):
                self._stretch_grid()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_layout()
        self._stretch_grid()

    def _apply_layout(self):
        wide = self.width() >= 900
        if wide == self._wide:
            return
        self._wide = wide
        # 具体高度统一交给 _do_stretch（此处只切换 widget 位置与列/行比例）
        if wide:
            self.grid.addWidget(self.hero, 0, 0, 1, 1)
            self.grid.addWidget(self.batch_card, 1, 0, 1, 1)
            self.grid.addWidget(self.rail, 0, 1, 2, 1)
            self.grid.setColumnStretch(0, 3)
            self.grid.setColumnStretch(1, 2)
        else:
            self.grid.addWidget(self.hero, 0, 0, 1, 2)
            self.grid.addWidget(self.batch_card, 1, 0, 1, 2)
            self.grid.removeWidget(self.rail)
            self.grid.addWidget(self.rail, 2, 0, 1, 2)
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 0)
        self._stretch_grid()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_layout()
        self._stretch_grid()

    def retranslate(self):
        self.t_round.setText(t("round_title"))
        self.t_pool.setText(t("pool_title"))
        self.btn_reset.setText(t("draw_reset_round"))
        self.btn_export.setText(t("draw_export"))
        self.btn_batch.setText(t("batch_draw_n", n=self.stepper.value()))
        for n, c in self.chips.items():
            c.setText(t("batch_count_unit", n=n))
        self.refresh()

    def _reset_round(self):
        if not self.store:
            return
        n = len(self.store.round_list())
        if n == 0:
            snack(self, t("snack_reset_none")); return
        if not ask(self, t("draw_reset_round"), t("confirm_reset_fmt", n=n),
                   yes=t("dlg_reset"), no=t("dlg_cancel")):
            return
        self.store.reset_round()
        self.refresh()
        self.num_label.set_rolling(False)
        self.num_label.set_text_color(COLORS["on_surface"])
        self.num_label.set_now("")
        self._set_name("")
        self.seal.hide()
        self._set_state("empty")
        self.result.set_watermark(True)
        snack(self, t("snack_reset_done"))

    def _export(self):
        if not self.store:
            return
        text = self.store.export_text()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.store.base_dir / "exports" / \
            f"{app_data.safe_filename(self.store.name)}_记录_{ts}.txt"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            snack(self, t("snack_export_ok", name=out.name), kind="success")
        except Exception:
            snack(self, t("snack_export_fail"), kind="error", duration=4200)


# ===========================================================================
# 记录页
# ===========================================================================

class HistoryPage(QWidget):
    history_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 18, 28, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self._t_title = QLabel(t("history_title"))
        self._t_title.setStyleSheet(serif_style(24, COLORS["on_surface"], 600) + "; background:transparent;")
        self.summary = QLabel("")
        self.summary.setStyleSheet(
            f"color:{COLORS['ink_faint']}; font-size:12px; background:transparent;")
        self.btn_manage = make_button(t("manage_records"), "", min_height=44)
        self.btn_manage.clicked.connect(self._manage)
        self.btn_export = make_button(t("export_txt"), "primary", min_height=44)
        self.btn_export.clicked.connect(self._export)
        head.addWidget(_page_kicker("02"))
        head.addSpacing(10)
        head.addWidget(self._t_title)
        head.addSpacing(12)
        head.addWidget(self.summary)
        head.addStretch(1)
        head.addWidget(self.btn_manage)
        head.addWidget(self.btn_export)
        lay.addLayout(head)
        lay.addWidget(hairline())

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [t("col_no"), t("col_time"), t("col_num"), t("col_name"), t("col_mode")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 64)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(4, 90)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        enable_touch_scroll(self.table)
        # 占比列自绘（原先 setCellWidget 会漏控件，见 PctBarDelegate 说明）
        self._pct_delegate = PctBarDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._pct_delegate)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.viewport().setAutoFillBackground(False)
        self.table.viewport().setStyleSheet("background:transparent;")
        self.table_card = PaperCard(self, radius=20, variant="elevated")
        tc = QVBoxLayout(self.table_card)
        tc.setContentsMargins(10, 6, 10, 8)
        tc.addWidget(self.table)
        lay.addWidget(self.table_card, 1)

        self._t_tip = QLabel(t("history_hint"))
        self._t_tip.setStyleSheet(
            f"color:{COLORS['ink_faint']}; font-size:11.5px; background:transparent;")
        lay.addSpacing(2)
        lay.addWidget(self._t_tip)

    def set_store(self, store: ClassStore):
        self.store = store
        self.refresh()
        fade_in(self.table, dur=240, delay=40)

    def retranslate(self):
        self._t_title.setText(t("history_title"))
        self._t_tip.setText(t("history_hint"))
        self.btn_export.setText(t("export_txt"))
        self.btn_manage.setText(t("manage_records"))
        self.table.setHorizontalHeaderLabels(
            [t("col_no"), t("col_time"), t("col_num"), t("col_name"), t("col_mode")])
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        records = self.store.history()
        rows = list(reversed(records))
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            c0 = QTableWidgetItem(str(len(rows) - i))
            c0.setTextAlignment(Qt.AlignCenter)
            c1 = QTableWidgetItem(str(r.get("time", "")))
            c2 = QTableWidgetItem(str(int(r.get("num", 0))).zfill(2))
            c2.setTextAlignment(Qt.AlignCenter)
            c3 = QTableWidgetItem(r.get("name") or "—")
            c4 = QTableWidgetItem(t("mode_advanced") if r.get("mode") == MODE_ADVANCED
                                  else t("mode_simple"))
            c4.setTextAlignment(Qt.AlignCenter)
            for ci, c in enumerate((c0, c1, c2, c3, c4)):
                self.table.setItem(i, ci, c)
        self.table.setUpdatesEnabled(True)
        self.summary.setText(t("count_items", n=len(records)))

    def _manage(self):
        if not self.store:
            return
        from .ui_dialogs import AdminPasswordDialog, HistoryCleanupDialog
        pwd = AdminPasswordDialog(self, self.store.base_dir)
        if not pwd.exec() or not pwd.verified:
            return
        dlg = HistoryCleanupDialog(self, self.store)
        if not dlg.exec():
            return
        if dlg.deleted_count:
            self.refresh()
            self.history_changed.emit()
            snack(self, t("clean_done_fmt", n=dlg.deleted_count,
                          name=dlg.archive_path.name if dlg.archive_path else "-"),
                  kind="success", duration=4200)

    def _export(self):
        if not self.store:
            return
        text = self.store.export_text()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.store.base_dir / "exports" / \
            f"{app_data.safe_filename(self.store.name)}_记录_{ts}.txt"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            snack(self, t("snack_export_ok", name=out.name), kind="success")
        except Exception:
            snack(self, t("snack_export_fail"), kind="error", duration=4200)


# ===========================================================================
# 统计页
# ===========================================================================

class StatsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 18, 28, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self._t_title = QLabel(t("stats_title"))
        self._t_title.setStyleSheet(serif_style(24, COLORS["on_surface"], 600) + "; background:transparent;")
        self.summary = QLabel("")
        self.summary.setStyleSheet(
            f"color:{COLORS['ink_faint']}; font-size:12px; background:transparent;")
        head.addWidget(_page_kicker("03"))
        head.addSpacing(10)
        head.addWidget(self._t_title)
        head.addStretch(1)
        head.addWidget(self.summary)
        lay.addLayout(head)
        lay.addWidget(hairline())

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [t("col_rank"), t("col_key"), t("col_count"), t("col_pct")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 200)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        enable_touch_scroll(self.table)
        # 占比列自绘（原先 setCellWidget 会漏控件，见 PctBarDelegate 说明）
        self._pct_delegate = PctBarDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._pct_delegate)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.viewport().setAutoFillBackground(False)
        self.table.viewport().setStyleSheet("background:transparent;")
        self.table_card = PaperCard(self, radius=20, variant="elevated")
        tc = QVBoxLayout(self.table_card)
        tc.setContentsMargins(10, 6, 10, 8)
        tc.addWidget(self.table)
        lay.addWidget(self.table_card, 1)

    def set_store(self, store: ClassStore):
        self.store = store
        self.refresh()
        fade_in(self.table, dur=240, delay=40)

    def retranslate(self):
        self._t_title.setText(t("stats_title"))
        self.table.setHorizontalHeaderLabels(
            [t("col_rank"), t("col_key"), t("col_count"), t("col_pct")])
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        items = self.store.stats()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(items))
        for i, s in enumerate(items):
            c0 = QTableWidgetItem(str(s["rank"]))
            c0.setTextAlignment(Qt.AlignCenter)
            txt = s["display"]
            if not str(txt).startswith("号码"):
                txt = f"{int(s.get('num', 0)):02d}    {txt}"
            c1 = QTableWidgetItem(txt)
            c2 = QTableWidgetItem(str(s["count"]))
            c2.setTextAlignment(Qt.AlignCenter)
            c3 = QTableWidgetItem()
            c3.setData(Qt.UserRole, float(s["pct"]))
            self.table.setItem(i, 0, c0)
            self.table.setItem(i, 1, c1)
            self.table.setItem(i, 2, c2)
            self.table.setItem(i, 3, c3)
        self.table.setUpdatesEnabled(True)
        top = max((it["pct"] for it in items), default=0.0)
        self._pct_delegate.restart(top)   # 进度条重新生长（按最高者归一）
        self.summary.setText(f"{sum(s['count'] for s in items)}")

    def _set_total(self, total: int):
        self.summary.setText(str(total))


# ===========================================================================
# 配置页
# ===========================================================================

class ConfigPage(QWidget):
    settings_changed = Signal()

    ROWS = [
        ("row_name", "name"), ("row_mode", "mode"), ("row_total", "total"),
        ("row_all", "all"), ("row_pool", "pool"),
        ("row_long", "long"), ("row_short", "short"),
        ("row_anti", "anti"), ("row_path", "path"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self.on_reconfigure = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        enable_touch_scroll(self.scroll)
        self.inner = QWidget()
        lay = QVBoxLayout(self.inner)
        lay.setContentsMargins(32, 18, 28, 16)
        lay.setSpacing(14)

        self._t_title = QLabel(t("config_title"))
        self._t_title.setStyleSheet(serif_style(24, COLORS["on_surface"], 600) + "; background:transparent;")
        hrow = QHBoxLayout()
        hrow.setSpacing(10)
        hrow.addWidget(_page_kicker("04"))
        hrow.addWidget(self._t_title)
        hrow.addStretch(1)
        lay.addLayout(hrow)
        self._t_sub = QLabel(t("config_sub"))
        self._t_sub.setStyleSheet(
            f"color:{COLORS['ink_faint']}; font-size:12px; background:transparent;")
        lay.addWidget(self._t_sub)
        lay.addWidget(hairline())

        sec_class = PaperCard(self.inner, radius=20, variant="elevated")
        sc = QVBoxLayout(sec_class)
        sc.setContentsMargins(20, 16, 20, 8)
        sc.setSpacing(8)
        sc.addWidget(_section_title(t("config_section_class")))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(0)
        sc.addLayout(self.grid)
        lay.addWidget(sec_class)

        lay.addSpacing(4)
        self.roster_card = PaperCard(self.inner, radius=20, variant="elevated")
        vv = QVBoxLayout(self.roster_card)
        vv.setContentsMargins(20, 16, 20, 16)
        vv.setSpacing(8)
        self.roster_head = _section_title(t("roster_title"))
        vv.addWidget(self.roster_head)
        self._t_rhint = QLabel(t("roster_hint"))
        self._t_rhint.setWordWrap(True)
        self._t_rhint.setStyleSheet(
            f"color:{COLORS['ink_soft']}; font-size:12.5px; background:transparent;")
        vv.addWidget(self._t_rhint)
        self.roster_list = WrapLabel("")
        self.roster_list.setStyleSheet(
            f"color:{COLORS['ink']}; font-size:13px; background:transparent;"
            f"border-left:2px solid {COLORS['line_soft']}; padding-left:12px;")
        vv.addWidget(self.roster_list)
        rbtn = QHBoxLayout()
        self.btn_edit_roster = make_button(t("edit_roster"), "", min_height=44)
        self.btn_edit_roster.clicked.connect(self._edit_roster)
        rbtn.addWidget(self.btn_edit_roster)
        rbtn.addStretch(1)
        vv.addLayout(rbtn)
        lay.addWidget(self.roster_card)

        lay.addSpacing(4)
        self.anti_card = PaperCard(self.inner, radius=20, variant="elevated")
        v2 = QVBoxLayout(self.anti_card)
        v2.setContentsMargins(20, 16, 20, 16)
        v2.setSpacing(10)
        v2.addWidget(_section_title(t("anti_title")))
        self.sw_anti_label = QLabel(t("anti_label"))
        self.sw_anti_label.setWordWrap(True)
        self.sw_anti_label.setStyleSheet(
            f"color:{COLORS['ink_soft']}; font-size:13px; background:transparent;")
        from PySide6.QtWidgets import QSpinBox as _SB
        self.chk_anti = SwitchControl(True)
        self.spin_anti = _SB()
        self.spin_anti.setRange(app_data.ANTI_DUP_MIN_HOURS, app_data.ANTI_DUP_MAX_HOURS)
        self.spin_anti.setSuffix(" " + t("unit_hours"))
        self.spin_anti.setMinimumHeight(44)
        self.spin_anti.setFixedWidth(140)
        self.spin_anti.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.sw_anti_label, 1)
        row.addWidget(self.spin_anti)
        row.addSpacing(8)
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
        lay.addWidget(self.anti_card)
        lay.addStretch(1)

        self.scroll.setWidget(self.inner)
        outer.addWidget(self.scroll, 1)

    def set_store(self, store: ClassStore, cfg: dict):
        self.store = store
        self.cfg = cfg
        self.refresh()

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
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                # 先 hide 再 deleteLater：deleteLater 只是排队，旧控件在被真正
                # 销毁前依然可见、依然按旧几何绘制，会和新行叠成一团乱字。
                w.hide()
                w.deleteLater()

        students = self.store.get_students(cfg)
        name_of = {s["num"]: s.get("name", "") for s in students}
        long_n = self.store.long_exempt()
        short_n = self.store.short_exempt()
        cool_n = self.store.cooling_nums(cfg)
        ls, ss, cs = set(long_n), set(short_n), set(cool_n)
        pool = [s for s in students if s["num"] not in ls and s["num"] not in ss
                and s["num"] not in cs]

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

        r = 0
        for i, (label_key, key) in enumerate(self.ROWS):
            l = QLabel(t(label_key))
            l.setFixedWidth(110)
            l.setStyleSheet(
                f"color:{COLORS['ink_faint']}; font-size:12.5px; background:transparent;")
            l.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            # 值可能折行（摇号池详情、屏蔽名单、配置文件路径），用 WrapLabel
            # 让它把「折行后需要的高度」写进 minimumHeight，否则会压住下一行
            v = WrapLabel(val(key))
            v.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setStyleSheet(
                f"color:{COLORS['ink']}; font-size:13.5px; background:transparent;"
                "padding:12px 0 12px 0;")
            l.setStyleSheet(l.styleSheet() + "padding-top:13px;")
            self.grid.addWidget(l, r, 0)
            self.grid.addWidget(v, r, 1)
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background:{COLORS['line_soft']}; border:none;")
            self.grid.addWidget(line, r + 1, 0, 1, 2)
            r += 2
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(1, 220)
        # 行高按「真实列宽」再算一次：构建阶段列宽还没定，WrapLabel 用的是
        # 临时宽度，算出来会偏大或偏小。这里等布局跑完（0ms 定时器）统一收紧。
        QTimer.singleShot(0, self._fit_rows)

        names = self.store.roster_read()
        advanced = cfg.get("mode") == MODE_ADVANCED
        self.roster_head.setVisible(advanced)
        self.roster_card.setVisible(advanced)
        if advanced:
            shown = "　".join(f"{i + 1}. {n}" for i, n in enumerate(names))
            self.roster_list.setText(shown if names else t("roster_empty"))
        self.chk_anti.setChecked(bool(cfg.get("anti_dup_enabled", True)), animate=False)
        self.spin_anti.setValue(int(cfg.get("anti_dup_hours", 24)))
        self.spin_anti.setEnabled(bool(cfg.get("anti_dup_enabled", True)))

    def _fit_rows(self):
        self.grid.activate()
        for v in self.findChildren(WrapLabel):
            v.fit()
        self.grid.activate()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 窗口改宽/改窄后，折行行数会变，行高必须跟着重算
        QTimer.singleShot(0, self._fit_rows)

    def _on_anti_toggle(self, checked: bool):
        if not self.store:
            return
        self.spin_anti.setEnabled(checked)
        cfg = self.store.load_config()
        cfg["anti_dup_enabled"] = checked
        self.store.save_config(cfg)
        self.cfg = cfg
        self.refresh()
        self.settings_changed.emit()

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
        self._t_sub.setText(t("config_sub"))
        self._t_rhint.setText(t("roster_hint"))
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
            self.cfg = self.store.load_config()
            self.refresh()


# ===========================================================================
# 屏蔽页
# ===========================================================================

class ShieldPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.store: ClassStore | None = None
        self.cfg: dict = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 18, 28, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self._t_title = QLabel(t("shield_title"))
        self._t_title.setStyleSheet(serif_style(24, COLORS["on_surface"], 600) + "; background:transparent;")
        head.addWidget(_page_kicker("05"))
        head.addSpacing(10)
        head.addWidget(self._t_title)
        head.addStretch(1)
        lay.addLayout(head)

        self._t_tip = QLabel(t("shield_hint"))
        self._t_tip.setWordWrap(True)
        self._t_tip.setStyleSheet(
            f"color:{COLORS['ink_soft']}; font-size:12px; background:transparent;")
        lay.addWidget(self._t_tip)
        lay.addWidget(hairline())

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [t("col_status"), t("col_num"), t("col_name"), t("col_note")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        enable_touch_scroll(self.table)
        # 占比列自绘（原先 setCellWidget 会漏控件，见 PctBarDelegate 说明）
        self._pct_delegate = PctBarDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._pct_delegate)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.viewport().setAutoFillBackground(False)
        self.table.viewport().setStyleSheet("background:transparent;")
        self.table_card = PaperCard(self, radius=20, variant="elevated")
        tc = QVBoxLayout(self.table_card)
        tc.setContentsMargins(10, 6, 10, 8)
        tc.addWidget(self.table)
        lay.addWidget(self.table_card, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
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
        self.summary.setStyleSheet(
            f"color:{COLORS['ink_faint']}; font-size:12px; background:transparent;")
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
        fade_in(self.table, dur=240, delay=40)

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
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(students))
        for i, s in enumerate(students):
            num, name = s["num"], s.get("name", "")
            if num in long_n:
                status, color = t("status_long"), COLORS["primary"]
            elif num in short_n:
                status, color = t("status_short"), COLORS["camel"]
            else:
                status, color = t("status_normal"), COLORS["outline"]
            c0 = QTableWidgetItem(status)
            c0.setForeground(QColor(color))
            c1 = QTableWidgetItem(f"{num:02d}")
            c1.setTextAlignment(Qt.AlignCenter)
            c2 = QTableWidgetItem(name or t("unnamed"))
            c3 = QTableWidgetItem(t("note_never") if num in long_n else
                                  (t("note_today") if num in short_n else ""))
            c3.setForeground(QColor(COLORS["outline"]))
            self.table.setItem(i, 0, c0)
            self.table.setItem(i, 1, c1)
            self.table.setItem(i, 2, c2)
            self.table.setItem(i, 3, c3)
        self.table.setUpdatesEnabled(True)
        self.summary.setText(t("shield_summary", total=len(students),
                               long=len(long_n), short=len(short_n)))

    def _selected_nums(self) -> list[int]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        out = []
        for r in rows:
            it = self.table.item(r, 1)
            if it:
                out.append(int(it.text()))
        return out

    def _pick(self, kind: str, add: bool):
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
            snack(self, t("snack_select_first")); return
        cur = set(self.store.long_exempt() if kind == "long" else self.store.short_exempt())
        if add:
            cur.update(nums)
        else:
            cur.difference_update(nums)
        if kind == "long":
            self.store.set_long_exempt(sorted(cur))
        else:
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
