# -*- coding: utf-8 -*-
"""
桌面悬浮球 · 迷你抽号卡 · 全屏抽号层 · 托盘常驻
=========================================================================
设计说明（与主界面共用一套「宋体 + 1px 描边 + 克制光效」语言）：

- 悬浮球：贴边常驻，白色纸面圆盘 + 1px 描边 + 外圈极淡进度弧；
  鼠标移入才亮起，抽号中进度弧变成一段缓慢旋转的弧线。
- 单击小球展开迷你卡；再点小球收起。卡片从贴边一侧「抽」出来
  （裁切展开，不是整窗缩放），全部内容只在展开到 85% 后才接受点击，
  避免动画途中误触。
- 双击小球：所有屏幕一起压暗 → 滚号 → 落定光环 → 结果 → 压暗退回 0，
  最后才隐藏窗口，屏幕亮度完整恢复。
- 长按 0.34s（或按住后明显拖动）进入拖拽，松手吸附到最近的水平边缘；
  位置与显隐状态写进 float_state.json（软件目录，不写系统盘）。
- 主窗口是当前活动窗口（含其模态弹窗）时，小球自动贴边隐藏；
  用户可在托盘里彻底关闭小球。
- 所有抽号都走 ClassStore.record_draws，与主界面共用同一份
  current_round / history / anti_duplicate，不产生第二套记录。
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from pathlib import Path

from PySide6.QtCore import (Qt, QObject, QPoint, QPointF, QRectF,
                            QTimer, QPropertyAnimation, QParallelAnimationGroup,
                            QSequentialAnimationGroup, QEasingCurve, Property)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QFontMetricsF,
                           QGuiApplication, QIcon, QPainter, QPainterPath,
                           QPen, QBrush, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu)

from . import app_data
from .lang import t
from .theme import COLORS, display_font
from .ui_widgets import paint_icon

# ---------------------------------------------------------------------------
# 尺寸与节奏
# ---------------------------------------------------------------------------
BALL_WIN = 76            # 悬浮球窗口（含 9px 透明光晕边）
BALL_R = 29.0            # 可见圆盘半径
CARD_W, CARD_H = 300, 356
CARD_R = 22
GAP = 1                  # 卡片与球窗口的贴合量（可见间距约 8px）
EDGE_OFF = -6            # 允许球贴到屏幕边缘外 6px（视觉上正好压边）
LONG_PRESS_MS = 340      # 长按进入拖拽
DRAG_SLOP = 6            # 按住后移动超过该距离也直接进入拖拽
CLICK_DELAY_MS = 110     # 单击延迟，给快速双击让路

OVERLAY_PANEL_W, OVERLAY_PANEL_H = 560, 392


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _ease_out_cubic(x):
    x = _clamp(x, 0.0, 1.0)
    return 1.0 - (1.0 - x) ** 3


def _ease_out_quint(x):
    x = _clamp(x, 0.0, 1.0)
    return 1.0 - (1.0 - x) ** 5


def _ease_in_cubic(x):
    x = _clamp(x, 0.0, 1.0)
    return x * x * x


def _font(px: float, weight: int = 400, spacing: float = 0.0) -> QFont:
    f = display_font(max(8, int(round(px))), weight)
    if spacing:
        try:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(spacing))
        except Exception:
            pass
    return f


def _fmt_num(num: int) -> str:
    return f"{num:02d}" if num < 100 else str(num)


def _tray_icon() -> QIcon:
    """优先用应用图标；源码运行时从 assets 读，保证托盘不是空白。"""
    ic = QApplication.windowIcon()
    if ic is not None and not ic.isNull():
        return ic
    try:
        import sys
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        p = base / "assets" / "app_icon.ico"
        if p.exists():
            return QIcon(str(p))
    except Exception:
        pass
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(COLORS["primary"]))
    p.drawEllipse(QRectF(4, 4, 56, 56))
    p.setPen(QColor("#FFFFFF"))
    p.setFont(_font(30, 600))
    p.drawText(QRectF(4, 4, 56, 56), Qt.AlignCenter, "抽")
    p.end()
    return QIcon(pm)


# ===========================================================================
# 悬浮球
# ===========================================================================

class BallWindow(QWidget):
    """贴边悬浮球：单击展开卡片、双击全屏抽号、长按拖动。"""

    def __init__(self, dock: "FloatDock"):
        super().__init__(None)
        self.dock = dock
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus |
                            Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(BALL_WIN, BALL_WIN)
        self.setCursor(Qt.PointingHandCursor)

        self._hover = 0.0
        self._press = 0.0
        self._breath = 0.0
        self._spin = 0.0
        self._running = False
        self._shown = False
        self._hiding = False
        self._anim = None
        self._rest_pos = QPoint(0, 0)

        self._pressing = False
        self._press_global = QPoint()
        self._win_origin = QPoint()
        self._dragging = False
        self._suppress_click = False
        self._click_token = 0

        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(LONG_PRESS_MS)
        self._hold.timeout.connect(self._begin_drag)

        self._breath_timer = QTimer(self)
        self._breath_timer.setInterval(90)
        self._breath_timer.timeout.connect(self._tick_breath)

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(40)
        self._spin_timer.timeout.connect(self._tick_spin)

        self._hover_anim = None

    # ---- 属性 ----
    def get_hover(self): return self._hover
    def set_hover(self, v):
        self._hover = float(v)
        self.update()
    hover = Property(float, get_hover, set_hover)

    def get_press(self): return self._press
    def set_press(self, v):
        self._press = float(v)
        self.update()
    press = Property(float, get_press, set_press)

    # ---- 状态 ----
    def set_running(self, on: bool):
        self._running = bool(on)
        if on:
            self._spin_timer.start()
        else:
            self._spin_timer.stop()
            self._spin = 0.0
        self.update()

    def side(self) -> str:
        scr = self.dock.screen_at(self.geometry().center())
        avail = scr.availableGeometry()
        return "left" if self.geometry().center().x() < avail.center().x() else "right"

    def _tick_breath(self):
        # 3.6 秒一轮的呼吸；只驱动一个 76px 的小窗，开销可忽略
        self._breath = (self._breath + 90.0 / 3600.0) % 1.0
        if self.isVisible():
            self.update()

    def _tick_spin(self):
        self._spin = (self._spin + 0.055) % 1.0
        if self.isVisible():
            self.update()

    def _anim_hover(self, end: float, dur: int):
        if self._hover_anim is not None:
            self._hover_anim.stop()
        a = QPropertyAnimation(self, b"hover", self)
        a.setStartValue(float(self._hover))
        a.setEndValue(float(end))
        a.setDuration(dur)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start()
        self._hover_anim = a

    # ---- 位置与显隐 ----
    def restore(self, data: dict):
        scr = None
        x, y = data.get("x"), data.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            scr = QGuiApplication.screenAt(
                QPoint(int(x) + BALL_WIN // 2, int(y) + BALL_WIN // 2))
        if scr is None:
            scr = QGuiApplication.primaryScreen()
        avail = scr.availableGeometry()
        side = data.get("side")
        if side not in ("left", "right"):
            if isinstance(x, (int, float)):
                side = "left" if x < avail.center().x() else "right"
            else:
                side = "left"
        if isinstance(y, (int, float)):
            yy = int(y)
        else:
            yy = avail.center().y() - BALL_WIN // 2
        yy = _clamp(yy, avail.top() + EDGE_OFF, avail.bottom() - BALL_WIN + 6)
        xx = avail.left() if side == "left" else avail.right() - BALL_WIN + 1
        self.move(int(xx), int(yy))
        self._rest_pos = self.pos()

    def snap_to_edge(self, animate: bool = True):
        scr = self.dock.screen_at(self.geometry().center())
        avail = scr.availableGeometry()
        side = self.side()
        x = avail.left() if side == "left" else avail.right() - BALL_WIN + 1
        y = _clamp(self.y(), avail.top() + EDGE_OFF,
                   avail.bottom() - BALL_WIN + 6)
        target = QPoint(int(x), int(y))
        self._rest_pos = target
        if not animate or not self.isVisible():
            self.move(target)
            return
        a = QPropertyAnimation(self, b"pos", self)
        a.setStartValue(self.pos())
        a.setEndValue(target)
        a.setDuration(220)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start()
        self._snap_anim = a

    def is_hiding(self) -> bool:
        return bool(self._hiding)

    def show_in(self, animate: bool = True):
        if self._shown and self.isVisible():
            return
        if self._anim is not None:
            self._anim.stop()
        self._hiding = False
        self._shown = True
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        if not self.isVisible():
            self.move(self._rest_pos)
            self.setWindowOpacity(0.0 if animate else 1.0)
            self.show()
        self.raise_()
        self._breath_timer.start()
        if not animate:
            self.setWindowOpacity(1.0)
            return
        side = self.side()
        dx = -24 if side == "left" else 24
        start = self._rest_pos + QPoint(dx, 0)
        self.move(start)
        self.setWindowOpacity(0.0)
        grp = QParallelAnimationGroup(self)
        pa = QPropertyAnimation(self, b"pos")
        pa.setStartValue(start)
        pa.setEndValue(self._rest_pos)
        pa.setDuration(380)
        pa.setEasingCurve(QEasingCurve.OutQuint)
        oa = QPropertyAnimation(self, b"windowOpacity")
        oa.setStartValue(0.0)
        oa.setEndValue(1.0)
        oa.setDuration(300)
        oa.setEasingCurve(QEasingCurve.OutCubic)
        grp.addAnimation(pa)
        grp.addAnimation(oa)
        grp.start()
        self._anim = grp

    def hide_out(self, animate: bool = True):
        # 正在收起时不要重复起动画：sync_visibility 每 180ms 轮询一次，
        # 若每次都重启动画，210ms 的淡出永远走不到 finished，窗口就一直可见。
        if self._hiding:
            return
        if not self._shown and not self.isVisible():
            return
        if self._anim is not None:
            self._anim.stop()
        self._hiding = True
        self._shown = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._hold.stop()
        self._dragging = False
        self.set_press(0.0)
        if not self.isVisible():
            return
        if not animate:
            self.hide()
            self.setWindowOpacity(1.0)
            self._hiding = False
            self._breath_timer.stop()
            return
        side = self.side()
        dx = -20 if side == "left" else 20
        grp = QParallelAnimationGroup(self)
        pa = QPropertyAnimation(self, b"pos")
        pa.setStartValue(self.pos())
        pa.setEndValue(self.pos() + QPoint(dx, 0))
        pa.setDuration(210)
        pa.setEasingCurve(QEasingCurve.InCubic)
        oa = QPropertyAnimation(self, b"windowOpacity")
        oa.setStartValue(self.windowOpacity())
        oa.setEndValue(0.0)
        oa.setDuration(200)
        oa.setEasingCurve(QEasingCurve.InCubic)
        grp.addAnimation(pa)
        grp.addAnimation(oa)
        grp.finished.connect(self._hide_done)
        grp.start()
        self._anim = grp

    def _hide_done(self):
        if self._shown:
            self._hiding = False
            return
        self._hiding = False
        self.hide()
        self.setWindowOpacity(1.0)
        self.move(self._rest_pos)
        self._breath_timer.stop()

    def nudge(self):
        """摇号池空时轻轻晃一下，代替报错弹窗。"""
        if not self.isVisible():
            return
        base = self.pos()
        grp = QSequentialAnimationGroup(self)
        prev = 0
        for dx in (-5, 5, -3, 3, 0):
            a = QPropertyAnimation(self, b"pos")
            a.setStartValue(base + QPoint(prev, 0))
            a.setEndValue(base + QPoint(dx, 0))
            a.setDuration(48)
            a.setEasingCurve(QEasingCurve.InOutSine)
            grp.addAnimation(a)
            prev = dx
        grp.start()
        self._anim = grp

    # ---- 绘制 ----
    def enterEvent(self, e):
        super().enterEvent(e)
        self._anim_hover(1.0, 180)

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._anim_hover(0.0, 220)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        c = QPointF(BALL_WIN / 2.0, BALL_WIN / 2.0)
        lift = -1.2 * self._hover
        p.translate(0, lift)
        scale = 1.0 - 0.045 * self._press
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)

        # 桌面上的柔和落影：只在球下方，避免像贴纸
        sh = QRadialGradient(QPointF(c.x(), c.y() + 7), BALL_R + 7)
        sh.setColorAt(0.0, QColor(20, 26, 34, 34))
        sh.setColorAt(0.62, QColor(20, 26, 34, 15))
        sh.setColorAt(1.0, QColor(20, 26, 34, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sh))
        p.drawEllipse(QPointF(c.x(), c.y() + 4), BALL_R + 5, BALL_R + 4)

        # 呼吸光晕：0.035~0.085，几乎察觉不到，但画面不会死
        breath = 0.5 - 0.5 * math.cos(self._breath * 2 * math.pi)
        halo_a = (0.035 + 0.045 * breath) + 0.05 * self._hover
        halo = QRadialGradient(c, BALL_R + 9)
        halo.setColorAt(0.0, QColor(94, 120, 144, int(255 * halo_a)))
        halo.setColorAt(0.75, QColor(94, 120, 144, int(255 * halo_a * 0.55)))
        halo.setColorAt(1.0, QColor(94, 120, 144, 0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(c, BALL_R + 8, BALL_R + 8)

        # 白色纸面圆盘 + 1px 描边
        border = QColor(COLORS["accent_soft"] if self._hover > 0.45
                        else COLORS["card_border"])
        p.setBrush(QColor(COLORS["surface_container_lowest"]))
        p.setPen(QPen(border, 1.0))
        p.drawEllipse(c, BALL_R, BALL_R)

        # 内圈：像印章的细边，给圆盘一点层次
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(74, 96, 119, 18), 1.0))
        p.drawEllipse(c, BALL_R - 5.0, BALL_R - 5.0)

        # 外圈进度弧：本轮已抽 / 总人数；抽号中改成旋转弧
        arc_r = BALL_R + 4.0
        arc_rect = QRectF(c.x() - arc_r, c.y() - arc_r, arc_r * 2, arc_r * 2)
        if self._running:
            p.setPen(QPen(QColor(94, 120, 144, 190), 1.8, Qt.SolidLine,
                          Qt.RoundCap))
            start = int((90 - self._spin * 360) * 16)
            p.drawArc(arc_rect, start, -70 * 16)

        # 中心字：宋体「抽」，颜色随 hover 从墨蓝变强调蓝
        col = QColor(COLORS["primary"])
        if self._hover > 0.01:
            target = QColor(COLORS["accent"])
            col = QColor(
                int(col.red() + (target.red() - col.red()) * self._hover),
                int(col.green() + (target.green() - col.green()) * self._hover),
                int(col.blue() + (target.blue() - col.blue()) * self._hover))
        p.setPen(col)
        f = _font(25, 500, 1.0)
        p.setFont(f)
        p.drawText(QRectF(c.x() - BALL_R, c.y() - BALL_R - 1.5,
                          BALL_R * 2, BALL_R * 2), Qt.AlignCenter, "抽")

        p.end()

    # ---- 鼠标 ----
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.dock.block_ball():
            return
        self._pressing = True
        self._dragging = False
        self._suppress_click = False
        self._press_global = e.globalPosition().toPoint()
        self._win_origin = self.pos()
        self._click_token += 1
        self.set_press(1.0)
        self._hold.start()

    def mouseMoveEvent(self, e):
        if not self._pressing:
            return
        gp = e.globalPosition().toPoint()
        delta = gp - self._press_global
        if not self._dragging and delta.manhattanLength() > DRAG_SLOP:
            self._begin_drag()
        if not self._dragging:
            return
        scr = self.dock.screen_at(gp)
        avail = scr.availableGeometry()
        nx = self._win_origin.x() + delta.x()
        ny = self._win_origin.y() + delta.y()
        nx = _clamp(nx, avail.left() + EDGE_OFF - 8,
                    avail.right() - BALL_WIN + 9)
        ny = _clamp(ny, avail.top() + EDGE_OFF,
                    avail.bottom() - BALL_WIN + 6)
        self.move(int(nx), int(ny))

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self._hold.stop()
        self.set_press(0.0)
        was_drag = self._dragging
        self._dragging = False
        self._pressing = False
        self.setCursor(Qt.PointingHandCursor)
        if was_drag:
            self.snap_to_edge(animate=True)
            self.dock.save_state()
            return
        if self._suppress_click:
            self._suppress_click = False
            return
        if self.dock.block_ball():
            return
        # 110ms 后再执行单击：足够让快速双击取消展开，
        # 又不会让人感到延迟。
        token = self._click_token
        QTimer.singleShot(CLICK_DELAY_MS,
                          lambda: self._do_single_click(token))

    def _do_single_click(self, token: int):
        if token != self._click_token or self._suppress_click:
            return
        self.dock.toggle_card()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self._hold.stop()
        self._suppress_click = True
        self._click_token += 1
        self._dragging = False
        self.set_press(0.0)
        if self.dock.block_ball():
            return
        self.dock.quick_draw()

    def _begin_drag(self):
        if not self._pressing or self._dragging:
            return
        if self.dock.block_ball():
            return
        self._dragging = True
        self._suppress_click = True
        self.setCursor(Qt.ClosedHandCursor)
        self.set_press(0.55)
        self.dock.card.close(instant=True)


# ===========================================================================
# 迷你卡片
# ===========================================================================

class MiniCard(QWidget):
    """从球侧抽出的迷你抽号卡：只有「已抽 n 位」、抽号空白区、两个图标键。"""

    def __init__(self, dock: "FloatDock"):
        super().__init__(None)
        self.dock = dock
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus |
                            Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        self._open = False
        self._reveal = 0.0
        self._side = "left"
        self._anim = None
        self._count = 0
        self._state = "empty"          # empty / rolling / result
        self._num = ""
        self._prev = ""
        self._name = ""
        self._roll_t = 1.0
        self._name_t = 1.0
        self._halo = 0.0
        self._running = False
        self._busy = False
        self._pool: list[dict] = []
        self._result: dict | None = None
        self._hover_btn = -1
        self._pressed_btn = -1
        self._body_press = False
        self._reset_until = 0.0

        self._btn_reset = QRectF(20, 296, 40, 40)
        self._btn_main = QRectF(68, 296, 40, 40)

        self._timer = QTimer(self)
        self._timer.setInterval(38)
        self._timer.timeout.connect(self._tick)

        self._reveal_anim = QPropertyAnimation(self, b"reveal", self)
        self._reveal_anim.setEasingCurve(QEasingCurve.OutQuint)
        self._close_connected = False
        self._roll_anim = QPropertyAnimation(self, b"roll_t", self)
        self._roll_anim.setEasingCurve(QEasingCurve.OutQuint)
        self._roll_anim.setDuration(380)
        self._name_anim = QPropertyAnimation(self, b"name_t", self)
        self._name_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._name_anim.setDuration(320)
        self._halo_anim = QPropertyAnimation(self, b"halo", self)
        self._halo_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._halo_anim.setDuration(780)

    # ---- 属性 ----
    def get_reveal(self): return self._reveal
    def set_reveal(self, v):
        self._reveal = float(v)
        self.update()
    reveal = Property(float, get_reveal, set_reveal)

    def get_roll_t(self): return self._roll_t
    def set_roll_t(self, v):
        self._roll_t = float(v)
        self.update()
    roll_t = Property(float, get_roll_t, set_roll_t)

    def get_name_t(self): return self._name_t
    def set_name_t(self, v):
        self._name_t = float(v)
        self.update()
    name_t = Property(float, get_name_t, set_name_t)

    def get_halo(self): return self._halo
    def set_halo(self, v):
        self._halo = float(v)
        self.update()
    halo = Property(float, get_halo, set_halo)

    @property
    def is_open(self) -> bool:
        return self._open

    def set_count(self, n: int):
        self._count = max(0, int(n))
        self.update()

    # ---- 开关 ----
    def open_for(self, ball: BallWindow):
        if self._open:
            return
        self._open = True
        self._side = ball.side()
        self._place(ball)
        self._reset_until = 0.0
        self.refresh(restore=True)
        self._reveal = 0.0
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        ball.raise_()
        self._reveal_anim.stop()
        if self._close_connected:
            try:
                self._reveal_anim.finished.disconnect()
            except Exception:
                pass
            self._close_connected = False
        self._reveal_anim.setStartValue(0.0)
        self._reveal_anim.setEndValue(1.0)
        self._reveal_anim.setDuration(300)
        self._reveal_anim.start()

    def close(self, instant: bool = False):
        if not self._open and not self.isVisible():
            return
        self._open = False
        self._timer.stop()
        self._running = False
        self._busy = False
        self._hover_btn = -1
        self._pressed_btn = -1
        self._body_press = False
        self._reveal_anim.stop()
        self._roll_anim.stop()
        self._name_anim.stop()
        self._halo_anim.stop()
        if instant:
            self.hide()
            self._reveal = 0.0
            return
        self._reveal_anim.setStartValue(self._reveal)
        self._reveal_anim.setEndValue(0.0)
        self._reveal_anim.setDuration(210)
        self._reveal_anim.setEasingCurve(QEasingCurve.InCubic)
        if not self._close_connected:
            self._reveal_anim.finished.connect(self._close_done)
            self._close_connected = True
        self._reveal_anim.start()

    def _close_done(self):
        if self._open:
            return
        self.hide()
        self._reveal = 0.0
        if self._close_connected:
            try:
                self._reveal_anim.finished.disconnect()
            except Exception:
                pass
            self._close_connected = False

    def _place(self, ball: BallWindow):
        scr = self.dock.screen_at(ball.geometry().center())
        avail = scr.availableGeometry()
        if self._side == "left":
            x = ball.x() + BALL_WIN - GAP
        else:
            x = ball.x() - CARD_W + GAP
        y = ball.y() + BALL_WIN // 2 - CARD_H // 2
        x = _clamp(x, avail.left() + 8, avail.right() - CARD_W - 8)
        y = _clamp(y, avail.top() + 8, avail.bottom() - CARD_H - 8)
        self.move(int(x), int(y))

    # ---- 数据 ----
    def refresh(self, restore: bool = False):
        store = self.dock.win.store
        if store is None:
            self._count = 0
            self._state = "empty"
            self.update()
            return
        items = store.round_list()
        self._count = len(items)
        if self._running or self._busy:
            self.update()
            return
        if self._state == "empty" and items and restore:
            last = items[-1]
            try:
                num = int(last.get("num", 0))
            except (TypeError, ValueError):
                num = 0
            self._num = _fmt_num(num) if num else ""
            self._prev = ""
            self._name = str(last.get("name", "") or "")
            self._name_t = 1.0
            self._roll_t = 1.0
            self._halo = 0.0
            self._state = "result" if self._num else "empty"
        elif not items:
            self._state = "empty"
            self._num = ""
            self._prev = ""
            self._name = ""
            self._name_t = 1.0
            self._roll_t = 1.0
            self._halo = 0.0
        self.update()

    def reset_visual(self):
        self._timer.stop()
        self._running = False
        self._busy = False
        self._state = "empty"
        self._result = None
        self._num = ""
        self._prev = ""
        self._name = ""
        self._name_t = 1.0
        self._roll_t = 1.0
        self._halo = 0.0
        self._count = 0
        self._reset_until = 0.0
        self.update()

    # ---- 抽号 ----
    def toggle_draw(self):
        if not self._open or self._reveal < 0.85:
            return
        if self._busy:
            return
        if self._running:
            self.stop_draw()
        else:
            self.start_draw()

    def start_draw(self):
        store = self.dock.win.store
        cfg = self.dock.win.cfg
        if store is None or not cfg:
            self.dock.toast(t("float_not_ready"))
            return
        snap = store.pool_snapshot(cfg)
        if not snap["pool"]:
            self.dock.toast(t("float_pool_empty"))
            self.dock.ball.nudge()
            return
        self._pool = snap["pool"]
        self._result = None
        self._running = True
        self._busy = False
        self._state = "rolling"
        self._name = ""
        self._name_t = 1.0
        self._halo = 0.0
        self._prev = self._num
        self._roll_t = 1.0
        self._timer.start()
        self.dock.ball.set_running(True)
        self._tick()

    def _tick(self):
        if not self._running or not self._pool:
            return
        s = random.choice(self._pool)
        txt = _fmt_num(int(s.get("num", 0)))
        if txt != self._num:
            self._prev = self._num
            self._num = txt
        self.update()

    def stop_draw(self):
        if not self._running or not self._pool:
            return
        self._timer.stop()
        self._running = False
        self.dock.ball.set_running(False)
        res = random.choice(self._pool)
        self._result = res
        num = int(res.get("num", 0))
        name = str(res.get("name", "") or "")
        n = self.dock.record_draw(num, name)
        self._count = n
        self._prev = self._num
        self._num = _fmt_num(num)
        self._name = name
        self._name_t = 0.0
        self._roll_t = 0.0
        self._halo = 0.0
        self._state = "result"
        self._busy = True

        self._roll_anim.stop()
        self._roll_anim.setStartValue(0.0)
        self._roll_anim.setEndValue(1.0)
        self._roll_anim.start()
        self._name_anim.stop()
        self._name_anim.setStartValue(0.0)
        self._name_anim.setEndValue(1.0)
        self._name_anim.start()
        self._halo_anim.stop()
        self._halo_anim.setStartValue(0.0)
        self._halo_anim.setEndValue(1.0)
        self._halo_anim.start()
        QTimer.singleShot(520, self._end_busy)
        self.update()

    def _end_busy(self):
        self._busy = False
        self.update()

    # ---- 重置 / 打开主窗 ----
    def arm_reset(self):
        if self._count <= 0:
            self.dock.toast_text(t("snack_reset_none"))
            return
        now = time.perf_counter()
        if now < self._reset_until:
            self._reset_until = 0.0
            self.dock.reset_round()
            return
        self._reset_until = now + 2.6
        QTimer.singleShot(2700, self._disarm_reset)
        self.update()

    def _disarm_reset(self):
        self._reset_until = 0.0
        self.update()

    # ---- 鼠标 ----
    def _hit_btn(self, pos: QPointF) -> int:
        if self._btn_reset.contains(pos):
            return 0
        if self._btn_main.contains(pos):
            return 1
        return -1

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        self._pressed_btn = self._hit_btn(pos)
        self._body_press = self._pressed_btn < 0
        self.update()

    def mouseMoveEvent(self, e):
        hit = self._hit_btn(e.position())
        if hit != self._hover_btn:
            self._hover_btn = hit
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        hit = self._hit_btn(pos)
        pressed = self._pressed_btn
        was_body = self._body_press
        self._pressed_btn = -1
        self._body_press = False
        self._hover_btn = hit
        if self._reveal < 0.85:
            self.update()
            return
        if pressed >= 0 and pressed == hit:
            if pressed == 0:
                self.arm_reset()
            else:
                self.dock.open_main()
        elif was_body and hit < 0 and QRectF(10, 100, CARD_W - 20, 180).contains(pos):
            if self._reset_until:
                self._reset_until = 0.0
            self.toggle_draw()
        self.update()

    def leaveEvent(self, e):
        self._hover_btn = -1
        self.update()
        super().leaveEvent(e)

    # ---- 绘制 ----
    def paintEvent(self, event):
        r = self._reveal
        if r <= 0.002:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = QRectF(0.5, 0.5, CARD_W - 1, CARD_H - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, CARD_R, CARD_R)

        # 从贴边一侧展开：横向 0.22→1，纵向 0.72→1，内容用同一变换后的
        # 裁切路径做「擦出」，文字本身不会被压扁。
        anchor = QPointF(0 if self._side == "left" else CARD_W, CARD_H / 2)
        sx = 0.22 + 0.78 * r
        sy = 0.72 + 0.28 * r
        tr = QTransform()
        tr.translate(anchor.x(), anchor.y())
        tr.scale(sx, sy)
        tr.translate(-anchor.x(), -anchor.y())
        clip = tr.map(path)

        # 卡片纸面
        p.save()
        p.setTransform(tr, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["surface_container_lowest"]))
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(COLORS.get("card_border", "#DCE1EB")), 1.0))
        p.drawPath(path)
        p.restore()

        # 极淡的顶部光，让白纸不是死白
        p.save()
        p.setClipPath(clip)
        g = QRadialGradient(QPointF(CARD_W * 0.2, -CARD_H * 0.1), CARD_W * 0.95)
        g.setColorAt(0.0, QColor(232, 239, 246, 120))
        g.setColorAt(1.0, QColor(232, 239, 246, 0))
        p.fillRect(self.rect(), QBrush(g))
        p.restore()

        # 内容透明度跟在展开进度后面
        alpha = _clamp((r - 0.18) / 0.62, 0.0, 1.0)
        p.save()
        p.setClipPath(clip)
        p.setOpacity(alpha)
        self._paint_content(p)
        p.restore()
        p.end()

    def _paint_content(self, p: QPainter):
        # 顶部章节标 + 状态点
        f = _font(9.5, 500, 1.6)
        p.setFont(f)
        p.setPen(QColor(COLORS["outline"]))
        kick = t("float_kicker").upper()
        p.drawText(QRectF(20, 22, 160, 16), Qt.AlignLeft | Qt.AlignVCenter, kick)
        kx = 20 + QFontMetricsF(f).horizontalAdvance(kick) + 9
        p.setPen(QPen(QColor(COLORS["accent"]), 1.0))
        p.drawLine(QPointF(kx, 30.5), QPointF(kx + 22, 30.5))

        if self._running:
            pulse = 0.5 + 0.5 * math.sin(time.perf_counter() * 6.0)
            dot = QColor(COLORS["accent"])
            dot.setAlphaF(0.35 + 0.55 * pulse)
            p.setPen(Qt.NoPen)
            p.setBrush(dot)
            p.drawEllipse(QPointF(CARD_W - 24, 30), 2.6, 2.6)

        # 本轮已抽 n 位：标签与数字共用基线，数字用 30px 宋体
        base_y = 79.0
        x = 20.0
        f1 = _font(11.5, 400, 1.2)
        p.setFont(f1)
        p.setPen(QColor(COLORS["on_surface_variant"]))
        p.drawText(QPointF(x, base_y), t("float_drawn_label"))
        x += QFontMetricsF(f1).horizontalAdvance(t("float_drawn_label")) + 9
        num_txt = f"{self._count:02d}" if self._count < 100 else str(self._count)
        f2 = _font(31, 600)
        p.setFont(f2)
        p.setPen(QColor(COLORS["accent"] if self._count else COLORS["outline"]))
        p.drawText(QPointF(x, base_y), num_txt)
        x += QFontMetricsF(f2).horizontalAdvance(num_txt) + 7
        p.setFont(f1)
        p.setPen(QColor(COLORS["on_surface_variant"]))
        p.drawText(QPointF(x, base_y), t("float_drawn_unit"))

        # 分隔线
        p.setPen(QPen(QColor(COLORS["card_border"]), 1.0))
        p.drawLine(QPointF(20, 96.5), QPointF(CARD_W - 20, 96.5))

        body = QRectF(20, 104, CARD_W - 40, 172)
        if self._state == "rolling":
            self._paint_roll(p, QRectF(0, 118, CARD_W, 102), 88)
            p.setFont(_font(10, 400, 1.6))
            p.setPen(QColor(COLORS["outline"]))
            p.drawText(QRectF(0, 232, CARD_W, 20), Qt.AlignCenter,
                       t("float_hint_stop"))
            p.setPen(QPen(QColor(COLORS["accent"]), 1.0))
            p.drawLine(QPointF(CARD_W / 2 - 13, 226),
                       QPointF(CARD_W / 2 + 13, 226))
        elif self._state == "result" and self._num:
            self._paint_halo(p)
            self._paint_roll(p, QRectF(0, 112, CARD_W, 104), 88)
            if self._name:
                nm = self._name
                p.setFont(_font(17, 500, 1.4))
                c = QColor(COLORS["on_surface"])
                c.setAlphaF(self._name_t)
                p.setPen(c)
                p.drawText(QRectF(0, 212, CARD_W, 28), Qt.AlignCenter, nm)
                hint_y = 246
            else:
                hint_y = 224
            p.setFont(_font(9.5, 400, 1.4))
            p.setPen(QColor(COLORS["outline"]))
            p.drawText(QRectF(0, hint_y, CARD_W, 18), Qt.AlignCenter,
                       t("float_hint_again"))
        else:
            # 空态：骰子 + 一行提示，不放按钮
            paint_icon(p, "dice", QRectF(CARD_W / 2 - 18, 132, 36, 36),
                       COLORS["outline_variant"], width=1.5)
            p.setFont(_font(12.5, 400, 1.8))
            p.setPen(QColor(COLORS["on_surface_variant"]))
            p.drawText(QRectF(0, 184, CARD_W, 22), Qt.AlignCenter,
                       t("float_hint_start"))
            p.setFont(_font(9, 400, 1.5))
            p.setPen(QColor(COLORS["outline"]))
            p.drawText(QRectF(0, 208, CARD_W, 18), Qt.AlignCenter,
                       t("float_hint_double"))

        # 底部分隔线 + 两个图标键
        p.setPen(QPen(QColor(COLORS["card_border"]), 1.0))
        p.drawLine(QPointF(20, 284.5), QPointF(CARD_W - 20, 284.5))

        armed = time.perf_counter() < self._reset_until
        for i, (rect, glyph, tip) in enumerate((
                (self._btn_reset, "refresh", t("float_reset_tip")),
                (self._btn_main, "app_window", t("float_open_tip")))):
            hovered = self._hover_btn == i
            pressed = self._pressed_btn == i
            if i == 0 and armed:
                bg = QColor(COLORS["error_container"])
                border = QColor(COLORS["error"])
                fg = COLORS["error"]
            else:
                bg = QColor(COLORS["surface_container_high"] if (hovered or pressed)
                            else COLORS["surface_container_low"])
                border = QColor(COLORS["card_border"])
                fg = COLORS["primary"] if hovered else COLORS["on_surface_variant"]
            p.setPen(QPen(border, 1.0))
            p.setBrush(bg)
            p.drawEllipse(rect)
            paint_icon(p, glyph, rect.adjusted(10.5, 10.5, -10.5, -10.5), fg,
                       width=1.55)

        p.setFont(_font(8.5, 400, 1.5))
        if armed:
            p.setPen(QColor(COLORS["error"]))
            txt = t("float_reset_confirm")
        else:
            p.setPen(QColor(COLORS["outline"]))
            txt = "LUCKY  DRAW"
        p.drawText(QRectF(120, 296, CARD_W - 140, 40),
                   Qt.AlignRight | Qt.AlignVCenter, txt)

    def _paint_roll(self, p: QPainter, rect: QRectF, px: int):
        txt = self._num or "--"
        prev = self._prev
        tval = _clamp(self._roll_t, 0.0, 1.0)
        f = _font(px, 600)
        p.setFont(f)
        color = QColor(COLORS["accent"] if self._state == "result"
                       else COLORS["primary"])
        if self._running:
            ghost = QColor(color)
            ghost.setAlphaF(0.065)
            p.setPen(ghost)
            p.drawText(rect.translated(0, -11), Qt.AlignCenter, txt)
            p.drawText(rect.translated(0, 11), Qt.AlignCenter, txt)
            p.setPen(color)
            p.drawText(rect, Qt.AlignCenter, txt)
            return
        if prev and prev != txt and tval < 0.999:
            h = rect.height() * 0.56
            a1 = QColor(color)
            a1.setAlphaF(1.0 - tval)
            p.setPen(a1)
            p.drawText(rect.translated(0, -tval * h), Qt.AlignCenter, prev)
            a2 = QColor(color)
            a2.setAlphaF(tval)
            p.setPen(a2)
            p.drawText(rect.translated(0, (1.0 - tval) * h), Qt.AlignCenter, txt)
            return
        p.setPen(color)
        p.drawText(rect, Qt.AlignCenter, txt)

    def _paint_halo(self, p: QPainter):
        """卡片的落定反馈：一团柔光 + 一圈收拢的细环，控制在正文区内。"""
        k = _clamp(self._halo, 0.0, 1.0)
        if k <= 0.001:
            return
        c = QPointF(CARD_W / 2, 166)
        glow = QRadialGradient(c, 92)
        a = 0.13 * (1.0 - k) ** 1.2
        glow.setColorAt(0.0, QColor(94, 120, 144, int(255 * a)))
        glow.setColorAt(0.55, QColor(94, 120, 144, int(255 * a * 0.45)))
        glow.setColorAt(1.0, QColor(94, 120, 144, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(c, 92, 92)

        u = _ease_out_cubic(k)
        r = 58 + 26 * u
        col = QColor(COLORS["primary"])
        col.setAlphaF(max(0.0, 0.22 * (1.0 - u) ** 1.5))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, max(0.8, 1.6 * (1.0 - u))))
        p.drawEllipse(c, r, r)


# ===========================================================================
# 全屏压暗 + 抽号
# ===========================================================================

class DimOverlay(QWidget):
    """一块屏幕的压暗层；只有目标屏绘制结果（无卡片，字直接落在暗场上）。"""

    def __init__(self, screen):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus |
                            Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.ArrowCursor)
        self.setGeometry(screen.geometry())
        self._screen = screen
        self.is_content = False
        self.dim = 0.0
        self.alpha = 0.0
        self.panel_in = 0.0
        self.num = ""
        self.prev = ""
        self.roll_t = 1.0
        self.rolling = False
        self.name = ""
        self.name_t = 0.0
        self.halo = 0.0
        self.footer = ""
        self.footer_t = 0.0
        self.fade = 1.0

    def set_state(self, **kw):
        changed = False
        for k, v in kw.items():
            if getattr(self, k, None) != v:
                setattr(self, k, v)
                changed = True
        if changed:
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        # 压暗：底黑 + 轻微暗角，避免整屏死黑一片
        p.fillRect(self.rect(), QColor(9, 12, 17, int(255 * 0.70 * self.dim)))
        if self.dim > 0.01:
            vg = QRadialGradient(QPointF(w / 2, h * 0.46),
                                 max(w, h) * 0.62)
            vg.setColorAt(0.0, QColor(9, 12, 17, 0))
            vg.setColorAt(0.72, QColor(9, 12, 17, 0))
            vg.setColorAt(1.0, QColor(9, 12, 17, int(70 * self.dim)))
            p.fillRect(self.rect(), QBrush(vg))
            # 中心的柔暗区：文字直接落在暗场上，靠它保证对比，
            # 而不是再垫一张白卡。
            spot = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.46)
            spot.setColorAt(0.0, QColor(4, 6, 10, int(95 * self.dim)))
            spot.setColorAt(0.68, QColor(4, 6, 10, int(30 * self.dim)))
            spot.setColorAt(1.0, QColor(4, 6, 10, 0))
            p.fillRect(self.rect(), QBrush(spot))

        if not self.is_content or self.alpha <= 0.003:
            p.end()
            return

        c = QPointF(w / 2, h / 2)

        # 落定光环：直接铺在暗场上，不裁进任何卡片
        if self.halo > 0.001:
            hc = QPointF(c.x(), c.y() - 26)
            for delay, strength, width in ((0.0, 1.0, 2.2), (0.16, 0.5, 1.1)):
                u = (self.halo - delay) / (1.0 - delay)
                if u <= 0:
                    continue
                u = _clamp(u, 0.0, 1.0)
                r = 118 + 248 * _ease_out_cubic(u)
                col = QColor(COLORS["primary_container"])
                col.setAlphaF(max(0.0, 0.20 * strength * (1.0 - u) ** 1.5))
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(col, max(0.8, width * (1.0 - u))))
                p.drawEllipse(hc, r, r)

        p.save()
        p.setOpacity(self.alpha)
        s = 0.968 + 0.032 * self.panel_in
        p.translate(c)
        p.scale(s, s)
        p.translate(-c)
        p.translate(0, (1.0 - self.panel_in) * 12)

        # 章节标：浅蓝细字 + 一道短横，像杂志的栏目标记
        p.setFont(_font(11.5, 500, 5.6))
        p.setPen(QColor(COLORS["primary_container"]))
        p.drawText(QRectF(0, c.y() - 208, w, 22), Qt.AlignCenter,
                   t("overlay_kicker"))
        p.setPen(QPen(QColor(207, 228, 247, 110), 1.0))
        p.drawLine(QPointF(c.x() - 22, c.y() - 224),
                   QPointF(c.x() + 22, c.y() - 224))

        # 大数字（含滚动）
        num_rect = QRectF(0, c.y() - 158, w, 260)
        px = 190 if len(self.num) <= 2 else 142
        p.setFont(_font(px, 600))
        color = QColor("#F7F9FC")
        if self.rolling:
            ghost = QColor(207, 228, 247)
            ghost.setAlphaF(0.16)
            p.setPen(ghost)
            p.drawText(num_rect.translated(0, -26), Qt.AlignCenter, self.num)
            p.drawText(num_rect.translated(0, 26), Qt.AlignCenter, self.num)
            p.setPen(color)
            p.drawText(num_rect, Qt.AlignCenter, self.num)
        elif self.prev and self.prev != self.num and self.roll_t < 0.999:
            hh = num_rect.height() * 0.58
            a1 = QColor(color)
            a1.setAlphaF(1.0 - self.roll_t)
            p.setPen(a1)
            p.drawText(num_rect.translated(0, -self.roll_t * hh),
                       Qt.AlignCenter, self.prev)
            a2 = QColor(color)
            a2.setAlphaF(self.roll_t)
            p.setPen(a2)
            p.drawText(num_rect.translated(0, (1.0 - self.roll_t) * hh),
                       Qt.AlignCenter, self.num)
        else:
            p.setPen(color)
            p.drawText(num_rect, Qt.AlignCenter, self.num)

        # 细线
        p.setPen(QPen(QColor(169, 188, 205, 110), 1.0))
        p.drawLine(QPointF(c.x() - 66, c.y() + 116),
                   QPointF(c.x() + 66, c.y() + 116))

        # 滚动中：姓名位置先放一行状态字
        if self.rolling:
            p.setPen(QColor(169, 188, 205, 190))
            p.setFont(_font(10.5, 400, 3.2))
            p.drawText(QRectF(0, c.y() + 138, w, 22), Qt.AlignCenter,
                       t("draw_running"))

        # 姓名
        if self.name:
            nc = QColor("#F1F0F4")
            nc.setAlphaF(_clamp(self.name_t, 0.0, 1.0))
            p.setPen(nc)
            p.setFont(_font(29, 500, 3.0))
            p.drawText(QRectF(0, c.y() + 132, w, 40), Qt.AlignCenter, self.name)
            fy = c.y() + 190
        else:
            fy = c.y() + 148

        # 已记录
        fc = QColor(COLORS["outline_variant"])
        fc.setAlphaF(_clamp(self.footer_t, 0.0, 1.0))
        p.setPen(fc)
        p.setFont(_font(10.5, 400, 2.0))
        p.drawText(QRectF(0, fy, w, 20), Qt.AlignCenter, self.footer)
        p.restore()
        p.end()

class ScreenDraw(QObject):
    """所有屏幕一起压暗；目标屏出示结果卡。"""

    T_DIM_IN = 0.28
    T_PANEL = 0.06
    T_ROLL = 0.24
    T_SLOW = 1.26
    T_SETTLE = 1.58
    T_SETTLE_DUR = 0.40
    T_NAME = 1.84
    T_FOOT = 2.04
    T_HOLD_END = 3.34
    T_FADE = 0.42

    def __init__(self, dock: "FloatDock"):
        super().__init__(dock)
        self.dock = dock
        self.wins: list[DimOverlay] = []
        self.active = False
        self._content: DimOverlay | None = None
        self._store = None
        self._cfg = None
        self._result: dict | None = None
        self._pool: list[dict] = []
        self._t0 = 0.0
        self._last_roll = 0.0
        self._cur = ""
        self._prev = ""
        self._settled = False
        self._record_n = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def play(self) -> bool:
        win = self.dock.win
        store, cfg = win.store, win.cfg
        if store is None or not cfg:
            self.dock.toast(t("float_not_ready"))
            return False
        snap = store.pool_snapshot(cfg)
        if not snap["pool"]:
            self.dock.toast(t("float_pool_empty"))
            self.dock.ball.nudge()
            return False
        if self.active:
            self.stop_now(quiet=True)

        self._store, self._cfg = store, cfg
        self._pool = list(snap["pool"])
        self._result = random.choice(self._pool)
        self._cur = _fmt_num(int(self._result.get("num", 0)))
        self._prev = self._cur
        self._settled = False
        self._record_n = len(store.round_list())
        self._t0 = time.perf_counter()
        self._last_roll = 0.0
        self.dock.ball.hide_out(animate=True)
        self.dock.card.close(instant=True)
        self.dock.hide_toast()

        self.wins = []
        self._content = None
        target = self.dock.screen_at(self.dock.ball.geometry().center())
        for scr in QGuiApplication.screens():
            w = DimOverlay(scr)
            w.is_content = (scr is target) or (scr == target)
            if w.is_content:
                self._content = w
            self.wins.append(w)
        for w in self.wins:
            w.show()
            w.raise_()
        self.active = True
        self._timer.start()
        self._apply(0.0)
        return True

    def stop_now(self, quiet: bool = False):
        self._timer.stop()
        for w in self.wins:
            w.hide()
            w.deleteLater()
        self.wins = []
        self._content = None
        was = self.active
        self.active = False
        if was and not quiet:
            self.dock.after_overlay()

    # ---- 时钟 ----
    def _tick(self):
        t = time.perf_counter() - self._t0
        # 滚号节奏：前段快、后段慢，落定前能看清最后一个数
        if self.T_ROLL <= t < self.T_SETTLE:
            interval = 0.045 if t < self.T_SLOW else 0.085
            if t - self._last_roll >= interval:
                self._last_roll = t
                s = random.choice(self._pool)
                txt = _fmt_num(int(s.get("num", 0)))
                if txt != self._cur:
                    self._prev = self._cur
                    self._cur = txt
        if t >= self.T_SETTLE and not self._settled:
            self._settled = True
            if self._result is not None:
                self._prev = self._cur
                self._cur = _fmt_num(int(self._result.get("num", 0)))
                self._record_n = self.dock.record_draw(
                    int(self._result.get("num", 0)),
                    str(self._result.get("name", "") or ""))
        self._apply(t)
        if t >= self.T_HOLD_END + self.T_FADE + 0.05:
            self.stop_now()

    def _apply(self, sec: float):
        if not self.active:
            return
        dim_in = _ease_out_cubic(sec / self.T_DIM_IN)
        fade = 1.0 - _ease_in_cubic(_clamp(
            (sec - self.T_HOLD_END) / self.T_FADE, 0.0, 1.0))
        dim = dim_in * fade
        panel = _ease_out_quint(_clamp(
            (sec - self.T_PANEL) / 0.46, 0.0, 1.0))
        if sec < self.T_SETTLE:
            roll_t = 1.0
            rolling = sec >= self.T_ROLL
        else:
            roll_t = _ease_out_quint(_clamp(
                (sec - self.T_SETTLE) / self.T_SETTLE_DUR, 0.0, 1.0))
            rolling = False
        name_t = _clamp((sec - self.T_NAME) / 0.36, 0.0, 1.0)
        foot_t = _clamp((sec - self.T_FOOT) / 0.36, 0.0, 1.0)
        halo = _clamp((sec - (self.T_SETTLE + 0.02)) / 0.86, 0.0, 1.0)
        alpha = panel * fade
        footer = t("overlay_record_fmt", n=self._record_n)

        for w in self.wins:
            if w is self._content:
                w.set_state(dim=dim, alpha=alpha, panel_in=panel,
                            num=self._cur, prev=self._prev, roll_t=roll_t,
                            rolling=rolling, name=str(self._result.get("name", "")
                                                      if self._result else ""),
                            name_t=name_t, halo=halo, footer=footer,
                            footer_t=foot_t)
            else:
                if abs(w.dim - dim) > 0.002:
                    w.dim = dim
                    w.update()


# ===========================================================================
# 轻提示
# ===========================================================================

class FloatToast(QWidget):
    """球下方/上方的一条深色轻提示，2.2 秒后自己走。"""

    def __init__(self, dock: "FloatDock"):
        super().__init__(None)
        self.dock = dock
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus |
                            Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedHeight(44)
        self._text = ""
        self._anim = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_text(self, text: str, ms: int = 2200):
        self._text = text
        fm = QFontMetrics(_font(12.5, 400))
        w = max(180, min(360, fm.horizontalAdvance(text) + 44))
        self.setFixedWidth(w)
        scr = self.dock.screen_at(self.dock.ball.geometry().center())
        avail = scr.availableGeometry()
        ball = self.dock.ball
        x = ball.x() + BALL_WIN // 2 - w // 2
        x = _clamp(x, avail.left() + 10, avail.right() - w - 10)
        y = ball.y() - 54
        if y < avail.top() + 8:
            y = ball.y() + BALL_WIN + 10
        self.move(int(x), int(y))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(160)
        a.start()
        self._anim = a
        self._timer.start(ms)
        self.update()

    def hide_now(self):
        self._timer.stop()
        self.hide()

    def _fade_out(self):
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.setDuration(220)
        a.finished.connect(self.hide)
        a.start()
        self._anim = a

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(47, 48, 51, 246))
        p.drawRoundedRect(r, 12, 12)
        p.setBrush(QColor(177, 201, 227))
        p.drawEllipse(QPointF(18, self.height() / 2), 2.4, 2.4)
        p.setPen(QColor(241, 240, 244))
        p.setFont(_font(12.5, 400, 0.4))
        fm = QFontMetrics(p.font())
        txt = fm.elidedText(self._text, Qt.ElideRight, self.width() - 40)
        p.drawText(QRectF(28, 0, self.width() - 38, self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, txt)
        p.end()


# ===========================================================================
# 总控：托盘 + 状态同步
# ===========================================================================

class FloatDock(QObject):
    """悬浮球 / 卡片 / 全屏层 / 托盘的总控。"""

    def __init__(self, win, enable_tray: bool = True):
        super().__init__(win)
        self.win = win
        self.app = QApplication.instance()
        self.quitting = False
        self.ready = False
        self.user_visible = True
        self._grace_until = 0.0
        self._menu_open = False
        self._auto_token = 0

        self._state_path = Path(win.manager.base) / "float_state.json"
        data = self._load_state()
        self.user_visible = bool(data.get("visible", True))

        self.ball = BallWindow(self)
        self.ball.restore(data)
        self.card = MiniCard(self)
        self.overlay = ScreenDraw(self)
        self.toast = FloatToast(self)

        self.tray = None
        self.tray_menu = None
        self.act_open = None
        self.act_ball = None
        self.act_quit = None
        self._tray_hint_shown = False

        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._build_tray()

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(180)
        self._sync_timer.timeout.connect(self.sync_visibility)
        self._sync_timer.start()

        try:
            self.app.focusChanged.connect(self._on_focus)
        except Exception:
            pass

    # ---- 状态文件 ----
    def _load_state(self) -> dict:
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def save_state(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "x": int(self.ball.x()), "y": int(self.ball.y()),
                "side": self.ball.side(), "visible": bool(self.user_visible),
            }
            self._state_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception:
            pass

    # ---- 屏幕 ----
    def screen_at(self, pt: QPoint):
        scr = QGuiApplication.screenAt(pt)
        return scr or QGuiApplication.primaryScreen()

    def main_active(self) -> bool:
        w = QApplication.activeWindow()
        if w is not None:
            if w is self.win:
                return True
            try:
                if w.parent() is self.win or w.window().parent() is self.win:
                    return True
            except Exception:
                pass
        # 原生文件对话框（导入名单 / 导出）不是 Qt 控件，activeWindow 认不出来，
        # 这时主程序其实还在最前台。用前台窗口的进程号兜一层，悬浮窗自己除外。
        return self._fg_is_ours()

    def _fg_is_ours(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            hwnd = u.GetForegroundWindow()
            if not hwnd:
                return False
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) != os.getpid():
                return False
            own = set()
            for w in (self.ball, self.card):
                try:
                    own.add(int(w.winId()))
                except Exception:
                    pass
            return int(hwnd) not in own
        except Exception:
            return False

    def block_ball(self) -> bool:
        """球不接收操作：主窗口在前台 / 全屏抽号中 / 菜单打开。"""
        return (self.main_active() or self.overlay.active or self._menu_open
                or self.quitting)

    def round_progress(self):
        store = self.win.store
        if store is None:
            return 0.0, False
        try:
            total = int(self.win.cfg.get("total_count", 0))
            if total <= 0:
                return 0.0, False
            n = len(store.round_list())
            return _clamp(n / float(total), 0.0, 1.0), True
        except Exception:
            return 0.0, False

    # ---- 启动 / 显隐 ----
    def activate(self):
        self.ready = True
        self.card.refresh(restore=True)
        # 主窗口此时就在前台：按「前台自动隐藏」的约定不亮球；
        # 用户切走 / 关到托盘后，轮询会把它贴回屏幕边缘。
        self.sync_visibility()

    def sync_visibility(self):
        if not self.ready or self.quitting:
            return
        blocked = self.main_active() or self.overlay.active or self._menu_open
        want = self.user_visible and not blocked
        if want:
            if not self.ball.isVisible() and not self.ball.is_hiding():
                self.ball.show_in(animate=True)
        else:
            if self.ball.isVisible() or self.ball.is_hiding():
                self.ball.hide_out(animate=True)
            if self.card.is_open:
                self.card.close(instant=not self.main_active())

    def _on_focus(self, old, new):
        # 主窗口一拿到焦点就立刻收球；不等 180ms 轮询
        if new is self.win:
            if self.ball.isVisible():
                self.ball.hide_out(animate=True)
            if self.card.is_open:
                self.card.close(instant=True)

    def toggle_card(self):
        if self.block_ball():
            return
        if self.card.is_open:
            self.card.close()
        else:
            self.card.open_for(self.ball)

    # ---- 抽号落盘（唯一入口，主界面与悬浮球共用）----
    def record_draw(self, num: int, name: str) -> int:
        """悬浮球与全屏层唯一落盘入口：写的是主界面同一份 store。"""
        store = self.win.store
        cfg = self.win.cfg
        if store is None:
            return 0
        anti = bool(cfg.get("anti_dup_enabled", True))
        try:
            store.record_draws(
                [{"num": int(num), "name": name or ""}],
                cfg.get("mode", app_data.MODE_SIMPLE), anti_dup=anti)
        except Exception:
            pass
        # 主界面此刻在后台，刷新五个页要几十毫秒；推迟到落定动画之后，
        # 避免正好卡在数字定格的那一帧上。
        QTimer.singleShot(80, self.win.notify_external_draw)
        n = len(store.round_list())
        self.card.set_count(n)
        self._schedule_auto_reset(store)
        return n

    def _schedule_auto_reset(self, store):
        self._auto_token += 1
        token = self._auto_token
        QTimer.singleShot(3200, lambda: self._auto_reset(token, store))

    def _auto_reset(self, token: int, store):
        if token != self._auto_token or self.quitting:
            return
        if self.win.store is not store:
            return
        if self.main_active():
            return
        cfg = self.win.cfg
        snap = store.pool_snapshot(cfg)
        if snap["pool"] or snap["total"] <= 0:
            return
        if len(snap["long"] | snap["short"]) >= snap["total"]:
            return
        store.reset_round()
        self.win.notify_external_draw()
        self.card.reset_visual()
        if self.ball.isVisible():
            self.toast_text(t("float_auto_reset"))
        self._refresh_tray()

    def reset_round(self):
        store = self.win.store
        if store is None:
            return
        store.reset_round()
        self.win.notify_external_draw()
        self.card.reset_visual()
        self.toast_text(t("float_reset_done"))

    # ---- 全屏抽号 ----
    def quick_draw(self):
        if self.block_ball():
            return
        if self.card.is_open:
            self.card.close(instant=True)
        ok = self.overlay.play()
        if ok:
            self.ball.set_running(True)
            self.hide_toast()

    def after_overlay(self):
        self.ball.set_running(False)
        self.card.refresh()
        if self.user_visible and not self.main_active():
            self.ball.show_in(animate=True)

    # ---- 提示 ----
    def toast_text(self, text: str, ms: int = 2400):
        self.toast.show_text(text, ms)

    def hide_toast(self):
        self.toast.hide_now()

    # ---- 主窗口 ----
    def open_main(self):
        self.card.close(instant=True)
        self.ball.hide_out(animate=True)
        self.win.show_main()

    # ---- 托盘 ----
    def _build_tray(self):
        self.tray = QSystemTrayIcon(_tray_icon(), self)
        self.tray.setToolTip(t("app_title"))
        menu = QMenu()
        self.tray_menu = menu
        self.act_open = menu.addAction(t("tray_open"), self.open_main)
        self.act_ball = menu.addAction(t("tray_ball"))
        self.act_ball.setCheckable(True)
        self.act_ball.setChecked(self.user_visible)
        self.act_ball.toggled.connect(self._toggle_from_tray)
        menu.addSeparator()
        self.act_quit = menu.addAction(t("tray_quit"), self.quit_app)
        menu.aboutToShow.connect(self._menu_show)
        menu.aboutToHide.connect(self._menu_hide)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _toggle_from_tray(self, checked: bool):
        self.user_visible = bool(checked)
        self.save_state()
        if self.user_visible:
            self._grace_until = 0.0
            self.sync_visibility()
        else:
            self.card.close(instant=True)
            self.ball.hide_out(animate=True)
            self.hide_toast()

    def _refresh_tray(self):
        if self.act_ball is not None:
            self.act_ball.blockSignals(True)
            self.act_ball.setChecked(self.user_visible)
            self.act_ball.blockSignals(False)

    def _menu_show(self):
        self._menu_open = True
        if self.ball.isVisible():
            self.ball.hide_out(animate=True)

    def _menu_hide(self):
        self._menu_open = False

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_main()

    def notify_closed_to_tray(self):
        if self.tray is None:
            return
        if self._tray_hint_shown:
            return
        self._tray_hint_shown = True
        try:
            if self.tray.supportsMessages():
                self.tray.showMessage(t("tray_hint_title"), t("tray_hint"),
                                      QSystemTrayIcon.Information, 3200)
        except Exception:
            pass

    def retranslate(self):
        if self.tray:
            self.tray.setToolTip(t("app_title"))
        for act, key in ((self.act_open, "tray_open"),
                         (self.act_ball, "tray_ball"),
                         (self.act_quit, "tray_quit")):
            if act is not None:
                act.setText(t(key))
        self.ball.update()
        self.card.update()

    # ---- 退出 ----
    def quit_app(self):
        if self.quitting:
            return
        self.quitting = True
        self.save_state()
        self._sync_timer.stop()
        self.overlay.stop_now(quiet=True)
        self.card.close(instant=True)
        self.toast.hide_now()
        self.ball.hide_out(animate=False)
        if self.tray:
            self.tray.hide()
        self.win._force_quit = True
        try:
            self.win.close()
        except Exception:
            pass
        app_data.flush()
        self.app.quit()
