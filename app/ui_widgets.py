# -*- coding: utf-8 -*-
"""
控件层 v3：Material Design 3 组件
=========================================================================
设计要点
- 组件形态严格按 M3：filled / tonal / outlined / text 按钮，filter chip，
  navigation bar 药丸指示器，28dp 弹窗，surface container 色阶。
- 光效克制：只用在三处——主按钮的柔和主色投影、抽号数字背后的径向光晕、
  批量揭晓时卡片落定的光环。都不是霓虹，只是让界面「有空气感」。
- 动效连续：所有状态变化都走属性动画（0.1~0.55s，M3 emphasized 曲线），
  没有瞬变；列表/导航指示器用同一个浮点进度插值，颜色与位置一起过渡。
"""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, Property,
                            QRectF, QPoint, QPointF, QVariantAnimation, QTimer,
                            QParallelAnimationGroup, QSequentialAnimationGroup,
                            Signal, QEvent, QSize, QRect, QAbstractAnimation)
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QPainterPath, QBrush,
                           QPixmap, QFontMetrics, QLinearGradient, QRadialGradient,
                           QImage)
from PySide6.QtWidgets import (QFrame, QLabel, QPushButton, QWidget, QHBoxLayout,
                               QVBoxLayout, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QProgressBar, QDialog,
                               QListWidget, QListWidgetItem, QApplication,
                               QAbstractScrollArea, QScroller, QScrollerProperties,
                               QScrollArea, QGridLayout, QSizePolicy, QAbstractItemView,
                               QSpacerItem, QStyledItemDelegate)

from . import theme
from .motion import (pop_in as m_pop_in, pop_out as m_pop_out,
                     bounce as m_bounce, stagger as m_stagger,
                     flip_text as m_flip, burst as m_burst,
                     animate as m_animate, ease_out_quint,
                     prepare_entry as m_prepare_entry)
from .theme import (COLORS, SHAPE, STATE_HOVER, STATE_PRESS, MOTION,
                    standard, emphasized, emphasized_decelerate,
                    emphasized_accelerate, stamp, serif_style, display_font)


# ===========================================================================
# 小工具：混色 / 光晕 / 矢量图标
# ===========================================================================

def hairline(parent=None, color: str | None = None) -> QFrame:
    line = QFrame(parent)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{color or COLORS['outline_variant']}; border:none;")
    return line


def _mix(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    out = QColor(int(c1.red() + (c2.red() - c1.red()) * t),
                 int(c1.green() + (c2.green() - c1.green()) * t),
                 int(c1.blue() + (c2.blue() - c1.blue()) * t))
    out.setAlpha(int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))
    return out


_GLOW: dict = {}


def glow_pixmap(size: int, color: str, alpha: int = 90) -> QPixmap:
    """径向渐变的柔光贴图（缓存）。用于数字光晕、按钮聚光，比实时渐变省。"""
    size = max(8, int(size))
    key = (size, color, int(alpha))
    pm = _GLOW.get(key)
    if pm is not None:
        return pm
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QRadialGradient(size / 2, size / 2, size / 2)
    base = QColor(color)
    for stop, a in ((0.0, alpha), (0.38, alpha * 0.72), (0.66, alpha * 0.26),
                    (0.86, alpha * 0.06), (1.0, 0)):
        c = QColor(base)
        c.setAlpha(int(max(0, min(255, a))))
        g.setColorAt(stop, c)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(0, 0, size, size)
    p.end()
    if len(_GLOW) > 120:
        _GLOW.clear()
    _GLOW[key] = pm
    return pm


def paint_icon(p: QPainter, name: str, rect: QRectF, color: str | QColor,
               width: float = 1.9) -> None:
    """24×24 视口的线性图标（M3 风格：圆头、2dp 描边）。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    col = QColor(color)
    s = min(rect.width(), rect.height()) / 24.0
    p.translate(rect.center().x() - 12 * s, rect.center().y() - 12 * s)
    p.scale(s, s)
    pen = QPen(col, width / max(0.35, s), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def polyline(*pts):
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        p.drawPath(path)

    if name == "dice":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 4.5, 4.5)
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        for cx, cy in ((9, 9), (15, 9), (12, 12), (9, 15), (15, 15)):
            p.drawEllipse(QPointF(cx, cy), 1.35, 1.35)
    elif name == "history":
        p.drawEllipse(QRectF(3.6, 3.6, 16.8, 16.8))
        polyline((12, 7.4), (12, 12.2), (15.4, 14.2))
    elif name == "chart":
        p.setPen(QPen(col, 3.0 / max(0.35, s), Qt.SolidLine, Qt.RoundCap))
        line(6, 19, 6, 12.5)
        line(12, 19, 12, 7.5)
        line(18, 19, 18, 10.5)
    elif name == "tune":
        line(4, 8.2, 20, 8.2)
        line(4, 15.8, 20, 15.8)
        p.setBrush(QColor(COLORS["surface_container_high"]))
        p.drawEllipse(QPointF(9, 8.2), 2.5, 2.5)
        p.drawEllipse(QPointF(15, 15.8), 2.5, 2.5)
    elif name == "shield":
        path = QPainterPath(QPointF(12, 3.2))
        path.lineTo(19, 6.0)
        path.lineTo(19, 11.4)
        path.quadTo(19, 17.2, 12, 20.8)
        path.quadTo(5, 17.2, 5, 11.4)
        path.lineTo(5, 6.0)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "play":
        path = QPainterPath(QPointF(9.2, 6.2))
        path.lineTo(18.4, 12)
        path.lineTo(9.2, 17.8)
        path.closeSubpath()
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    elif name == "stop":
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(7.2, 7.2, 9.6, 9.6), 2.2, 2.2)
    elif name == "refresh":
        p.drawArc(QRectF(4, 4, 16, 16), 60 * 16, 270 * 16)
        polyline((16.4, 3.6), (16.4, 8.0), (12.0, 8.0))
    elif name == "download":
        line(12, 4, 12, 14.6)
        polyline((7.4, 10.6), (12, 15.2), (16.6, 10.6))
        line(5, 19.4, 19, 19.4)
    elif name == "plus":
        line(12, 5.4, 12, 18.6)
        line(5.4, 12, 18.6, 12)
    elif name == "minus":
        line(5.4, 12, 18.6, 12)
    elif name == "close":
        line(6.4, 6.4, 17.6, 17.6)
        line(17.6, 6.4, 6.4, 17.6)
    elif name == "check":
        polyline((5, 12.4), (9.6, 17), (19, 7.2))
    elif name == "lock":
        p.drawRoundedRect(QRectF(5, 10.4, 14, 9.6), 2.6, 2.6)
        p.drawArc(QRectF(8, 4.2, 8, 10.2), 0, 180 * 16)
    elif name == "trash":
        line(4.6, 7.2, 19.4, 7.2)
        polyline((9, 7.2), (9.4, 4.6), (14.6, 4.6), (15, 7.2))
        p.drawRoundedRect(QRectF(6.4, 7.2, 11.2, 12.6), 2.2, 2.2)
    elif name == "more":
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        for cx in (6.4, 12.0, 17.6):
            p.drawEllipse(QPointF(cx, 12), 1.65, 1.65)
    elif name == "chevron_down":
        polyline((7, 9.8), (12, 14.8), (17, 9.8))
    elif name == "arrow_left":
        polyline((14.6, 6), (8.6, 12), (14.6, 18))
    elif name == "sparkle":
        path = QPainterPath(QPointF(12, 3.6))
        path.quadTo(13.4, 9.0, 19.4, 12)
        path.quadTo(13.4, 15.0, 12, 20.4)
        path.quadTo(10.6, 15.0, 4.6, 12)
        path.quadTo(10.6, 9.0, 12, 3.6)
        path.closeSubpath()
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    p.restore()


# ===========================================================================
# 按钮
# ===========================================================================

_KIND_ALIAS = {
    "": "outlined", "primary": "filled", "filled": "filled", "fab": "fab",
    "tonal": "tonal", "elevated": "elevated", "outlined": "outlined",
    "ghost": "text", "text": "text", "action": "text",
    "action-primary": "filled", "danger": "danger", "error": "error",
    "icon": "icon",
}


class RippleButton(QPushButton):
    """M3 按钮：状态层 + 涟漪 + 轻微按压缩放；主按钮带一层柔和主色投影。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._ripples: list[dict] = []
        self._press = 0.0
        self._hover = 0.0
        self._uline = 0.0            # 兼容旧接口
        self._focus = 0.0
        self._sheen = -1.0           # 按钮流光进度（-1 关闭）
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_StyledBackground, False)
        for prop, name in (("press", "_press"), ("hover", "_hover"),
                           ("uline", "_uline"), ("focus", "_focus")):
            pass
        self._install_glow()

    # ---- 属性 ----
    def _prop(self, field, val):
        setattr(self, field, val)
        self.update()

    def get_press(self): return self._press
    def set_press(self, v): self._prop("_press", v)
    press = Property(float, get_press, set_press)

    def get_hover(self): return self._hover
    def set_hover(self, v): self._prop("_hover", v)
    hover = Property(float, get_hover, set_hover)

    def get_uline(self): return self._uline
    def set_uline(self, v): self._prop("_uline", v)
    uline = Property(float, get_uline, set_uline)

    def get_focus(self): return self._focus
    def set_focus(self, v): self._prop("_focus", v)
    focus = Property(float, get_focus, set_focus)

    def get_sheen(self): return self._sheen
    def set_sheen(self, v): self._prop("_sheen", v)
    sheen = Property(float, get_sheen, set_sheen)

    def _anim(self, prop: str, target: float, dur: int, curve=None):
        a = QPropertyAnimation(self, prop.encode(), self)
        a.setStartValue(float(getattr(self, f"_{prop}")))
        a.setEndValue(float(target))
        a.setDuration(dur)
        a.setEasingCurve(curve or standard())
        a.start()
        setattr(self, f"_anim_{prop}", a)

    def _animate(self, prop: str, dur: int, target: float = 1.0):
        """兼容旧调用。"""
        self._anim(prop, target, dur)

    def _kind(self) -> str:
        raw = str(self.property("mtype") or self.property("type") or "")
        return _KIND_ALIAS.get(raw, raw or "outlined")

    def _install_glow(self):
        pass  # 阴影改为 paintEvent 手绘，不再用 QGraphicsDropShadowEffect

    def start_breath(self, lo: float = 22, hi: float = 34, dur: int = 2400):
        """呼吸光：用 _breath 属性驱动 paintEvent 手绘柔光。"""
        self.stop_breath()
        a = QVariantAnimation(self)
        a.setStartValue(0.35)
        a.setKeyValueAt(0.5, 1.0)
        a.setEndValue(0.35)
        a.setDuration(dur)
        a.setEasingCurve(QEasingCurve.InOutSine)
        a.setLoopCount(-1)
        a.valueChanged.connect(lambda v: (setattr(self, "_breath_v", v), self.update()))
        a.start()
        self._breath = a

    def stop_breath(self):
        a = getattr(self, "_breath", None)
        if a is not None:
            a.stop()
            self._breath = None
        self._breath_v = 0.0
        self.update()

    def sweep(self, dur: int = 620):
        """一次从左到右的流光，用于点击后的即时反馈。"""
        if self._kind() not in ("filled", "fab", "tonal", "error"):
            return
        a = QPropertyAnimation(self, b"sheen", self)
        a.setStartValue(-0.35)
        a.setEndValue(1.35)
        a.setDuration(dur)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start()
        self._sheen_anim = a

    def _glow_to(self, blur: float, dur: int):
        eff = getattr(self, "_glow_eff", None)
        if eff is None:
            return
        if getattr(self, "_breath", None) is not None:
            return
        a = QPropertyAnimation(eff, b"blurRadius", self)
        a.setStartValue(eff.blurRadius())
        a.setEndValue(blur)
        a.setDuration(dur)
        a.setEasingCurve(standard())
        a.start()
        self._glow_anim = a

    def showEvent(self, event):
        super().showEvent(event)
        # 类型属性通常在构造之后才设置，这里补装柔光（延迟到本轮事件结束）
        QTimer.singleShot(0, self._install_glow)

    # ---- 事件 ----
    def enterEvent(self, event):
        super().enterEvent(event)
        self._anim("hover", 1.0, MOTION["quick"])
        self._glow_to(32, MOTION["base"])

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._anim("hover", 0.0, MOTION["quick"])
        self._glow_to(22, MOTION["base"])

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._anim("focus", 1.0, MOTION["short"])

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._anim("focus", 0.0, MOTION["quick"])

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._anim("press", 1.0, MOTION["instant"], emphasized_decelerate())
        entry = {"x": event.position().x(), "y": event.position().y(), "anim": None}
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(480)
        anim.setEasingCurve(emphasized_decelerate())
        entry["anim"] = anim
        anim.valueChanged.connect(lambda _: self.update())
        anim.finished.connect(lambda: self._ripples.remove(entry) if entry in self._ripples else None)
        self._ripples.append(entry)
        anim.start()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._anim("press", 0.0, MOTION["short"], stamp())
        if self.isEnabled() and event.button() == Qt.LeftButton:
            self.sweep()

    def sizeHint(self):
        fm = QFontMetrics(self._font())
        kind = self._kind()
        if kind == "fab":
            pad, h = 76, 58
        elif kind == "icon":
            pad, h = 0, 44
        elif kind == "filled":
            pad, h = 64, 58
        else:
            pad, h = 48, 46
        txt = self.text()
        if kind in ("filled", "fab") and len(txt) == 2:
            txt = "  ".join(txt)
        return QSize(fm.horizontalAdvance(txt) + pad,
                     max(h, fm.height() + 22))

    # ---- 配色 ----
    def _font(self) -> QFont:
        kind = self._kind()
        f = QFont(self.font())
        if kind == "fab":
            px, weight = 19, QFont.DemiBold
        elif kind == "filled":
            px, weight = 19, QFont.DemiBold
        elif kind == "text":
            px, weight = 14, QFont.Medium
        elif kind == "icon":
            px, weight = 18, QFont.Medium
        else:
            px, weight = 15, QFont.Medium
        if self.property("big"):
            px += 2
        f.setPixelSize(px)
        f.setWeight(QFont.Weight(weight))
        return f

    def _palette(self):
        kind = self._kind()
        disabled = not self.isEnabled()
        if disabled:
            if kind in ("filled", "fab", "error"):
                return QColor(COLORS["surface_container_highest"]), \
                    QColor(COLORS["on_surface"]), None, None
            return QColor(0, 0, 0, 0), QColor(COLORS["on_surface"]), \
                QColor(COLORS["outline_variant"]), None
        if kind in ("filled", "fab"):
            return QColor(COLORS["btn_ink"]), QColor("#FFFFFF"), None, (255, 255, 255)
        if kind == "error":
            return QColor(COLORS["error"]), QColor(COLORS["on_error"]), None, (255, 255, 255)
        if kind == "tonal":
            return QColor(COLORS["secondary_container"]), \
                QColor(COLORS["on_secondary_container"]), None, None
        if kind == "elevated":
            return QColor(COLORS["surface_container_lowest"]), \
                QColor(COLORS["primary"]), None, None
        if kind == "danger":
            return QColor(0, 0, 0, 0), QColor(COLORS["error"]), None, None
        if kind in ("text", "icon"):
            return QColor(0, 0, 0, 0), QColor(COLORS["primary"]), None, None
        return QColor(0, 0, 0, 0), QColor(COLORS["primary"]), \
            QColor(COLORS["outline"]), None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        kind = self._kind()
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = rect.height() / 2 if kind != "fab" else min(24.0, rect.height() / 2)
        if kind == "fab":
            radius = 26.0

        # M3 press: scale 0.98, hover: 1.008
        s = 1.0 - 0.02 * self._press + 0.008 * self._hover
        c = QPointF(self.width() / 2, self.height() / 2)
        p.translate(c)
        p.scale(s, s)
        p.translate(-c)

        bg, fg, border, layer_rgb = self._palette()

        # 内置底部暗影：完全在按钮 rect 内，不出 widget 边界，无裁切
        if kind in ("filled", "fab", "error") and self.isEnabled():
            glow = getattr(self, "_breath_v", 0.0)
            gr = QLinearGradient(rect.bottomLeft(), rect.bottomLeft() - QPointF(0, rect.height() * 0.45))
            sh = QColor(COLORS["btn_ink"] if kind != "error" else COLORS["error"])
            sh.setAlpha(int(42 + 18 * glow))
            gr.setColorAt(0.0, sh)
            sh.setAlpha(0)
            gr.setColorAt(1.0, sh)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(gr))
            path = QPainterPath()
            path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
            p.setClipPath(path)
            p.drawRect(rect)
            p.setClipping(False)

        # 纯色填充（M3 不用渐变）
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, radius, radius)

        # 状态层（M3 规范：hover 8%、press 12%）
        if self._hover > 0.01 or self._press > 0.01:
            if layer_rgb:
                layer = QColor(*layer_rgb)
            elif kind in ("filled", "fab", "error"):
                layer = QColor(255, 255, 255)
            else:
                layer = QColor(COLORS["primary"])
            alpha = 0.08 * self._hover + 0.12 * self._press
            layer.setAlphaF(min(0.15, alpha))
            p.setBrush(layer)
            p.drawRoundedRect(rect, radius, radius)

        if border is not None:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(border, 1.0))
            p.drawRoundedRect(rect.adjusted(0.4, 0.4, -0.4, -0.4), radius, radius)

        # 键盘焦点圈
        if self._focus > 0.02 and self.hasFocus():
            ring = QColor(COLORS["primary"])
            ring.setAlphaF(0.5 * self._focus)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(ring, 2.0))
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)

        # 涟漪
        if self._ripples:
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            p.save()
            p.setClipPath(path)
            max_r = math.hypot(rect.width(), rect.height())
            for r in self._ripples:
                anim = r["anim"]
                if anim is None or not anim.state():
                    continue
                v = float(anim.currentValue())
                col = QColor(255, 255, 255) if kind in ("filled", "fab", "error") \
                    else QColor(COLORS["primary"])
                col.setAlphaF(max(0.0, 0.12 * (1.0 - v)))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                rr = 8 + v * max_r * 0.62
                p.drawEllipse(QPointF(r["x"], r["y"]), rr, rr)
            p.restore()

        # 流光
        if -0.3 < self._sheen < 1.3 and kind in ("filled", "fab", "tonal", "error"):
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            p.save()
            p.setClipPath(path)
            bw = rect.width() * 0.28
            x = rect.left() - bw + self._sheen * (rect.width() + bw * 2)
            band = QRectF(x, rect.top(), bw, rect.height())
            grad = QLinearGradient(band.topLeft(), band.topRight())
            base = QColor(255, 255, 255) if kind in ("filled", "fab", "error") \
                else QColor(COLORS["on_secondary_container"])
            a_mid = 30 if kind in ("filled", "fab", "error") else 16
            c0 = QColor(base); c0.setAlpha(0)
            c1 = QColor(base); c1.setAlpha(a_mid)
            c2 = QColor(base); c2.setAlpha(0)
            grad.setColorAt(0.0, c0); grad.setColorAt(0.5, c1); grad.setColorAt(1.0, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRect(band)
            p.restore()

        # 文字（filled 加字距，杂志感）
        f = self._font()
        p.setFont(f)
        p.setPen(fg)
        txt = self.text()
        if kind in ("filled", "fab") and len(txt) == 2:
            txt = "  ".join(txt)  # 仅二字加字距：开 始 / 停 止
        p.drawText(QRectF(self.rect()), Qt.AlignCenter, txt)
        p.end()


def make_button(text: str, kind: str = "", min_height: int = 48) -> QPushButton:
    b = RippleButton(text)
    b.setMinimumHeight(min_height)
    b.setMinimumWidth(min_height)
    b.setProperty("type", kind or "outlined")
    b.setProperty("mtype", kind or "outlined")
    b.setCursor(Qt.PointingHandCursor)
    return b


class IconButton(QPushButton):
    """圆形 icon 按钮（M3）：用于步进器、返回、关闭等。"""

    def __init__(self, icon: str, parent=None, size: int = 40, tooltip: str = ""):
        super().__init__(parent)
        self._icon = icon
        self._hover = 0.0
        self._press = 0.0
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(tooltip)
        # 禁用 QPushButton 带 menu 时自动加的下拉箭头
        self.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")

    def get_hover(self): return self._hover
    def set_hover(self, v):
        self._hover = v; self.update()
    hover = Property(float, get_hover, set_hover)

    def enterEvent(self, e):
        super().enterEvent(e)
        self._go(1.0)

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._go(0.0)

    def _go(self, v):
        a = QPropertyAnimation(self, b"hover", self)
        a.setStartValue(self._hover); a.setEndValue(v)
        a.setDuration(MOTION["quick"]); a.setEasingCurve(standard()); a.start()
        self._a = a

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        if self._hover > 0.01:
            side = min(self.width(), self.height()) - 2
            sq = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
            c = QColor(COLORS["on_surface_variant"])
            c.setAlphaF(0.10 * self._hover)
            p.setPen(Qt.NoPen); p.setBrush(c)
            p.drawEllipse(sq)
        col = COLORS["on_surface_variant"] if self.isEnabled() else COLORS["outline_variant"]
        if self.isDown():
            col = COLORS["primary"]
        d = rect.width() * 0.62
        paint_icon(p, self._icon, QRectF(rect.center().x() - d / 2,
                                        rect.center().y() - d / 2, d, d), col, 2.2)
        p.end()


class IconGlyph(QWidget):
    """静态矢量图标（不响应鼠标），用于下拉箭头、列表前缀等。"""

    def __init__(self, icon: str, size: int = 18, color: str | None = None,
                 parent=None, width: float = 2.0):
        super().__init__(parent)
        self._icon = icon
        self._color = color or COLORS["on_surface_variant"]
        self._width = width
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_color(self, color: str):
        self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_icon(p, self._icon, QRectF(self.rect()), self._color, self._width)
        p.end()


class ChoiceChip(QPushButton):
    """M3 filter chip：未选描边、选中主色容器 + 勾选图标。"""

    def __init__(self, text: str, checked: bool = False, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setMinimumWidth(56)
        self._hover = 0.0
        self._t = 1.0 if checked else 0.0
        self.setAttribute(Qt.WA_Hover, True)
        self.toggled.connect(self._on_toggle)

    def get_hover(self): return self._hover
    def set_hover(self, v):
        self._hover = v; self.update()
    hover = Property(float, get_hover, set_hover)

    def get_t(self): return self._t
    def set_t(self, v):
        self._t = v; self.updateGeo = None; self.update()
    t = Property(float, get_t, set_t)

    def _on_toggle(self, on):
        a = QPropertyAnimation(self, b"t", self)
        a.setStartValue(self._t); a.setEndValue(1.0 if on else 0.0)
        a.setDuration(280); a.setEasingCurve(stamp())
        a.start(); self._a = a
        self.updateGeometry()

    def enterEvent(self, e):
        super().enterEvent(e)
        a = QPropertyAnimation(self, b"hover", self)
        a.setStartValue(self._hover); a.setEndValue(1.0)
        a.setDuration(MOTION["quick"]); a.setEasingCurve(standard()); a.start()
        self._h = a

    def leaveEvent(self, e):
        super().leaveEvent(e)
        a = QPropertyAnimation(self, b"hover", self)
        a.setStartValue(self._hover); a.setEndValue(0.0)
        a.setDuration(MOTION["quick"]); a.setEasingCurve(standard()); a.start()
        self._h = a

    def sizeHint(self):
        fm = QFontMetrics(self._font())
        extra = 22 if self.isChecked() else 0
        return QSize(fm.horizontalAdvance(self.text()) + 34 + extra, 38)

    def _font(self):
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.Medium)
        return f

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        on = self._t
        bg = _mix(QColor(0, 0, 0, 0), QColor(COLORS["secondary_container"]), on)
        if self._hover > 0.01:
            bg = _mix(bg, QColor(COLORS["secondary_container"]), 0.45 * self._hover * (1 - on))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 9, 9)
        border = _mix(QColor(COLORS["outline"]), QColor(COLORS["secondary_container"]), on)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(border, 1.0))
        p.drawRoundedRect(rect, 9, 9)

        f = self._font()
        p.setFont(f)
        fg = _mix(QColor(COLORS["on_surface_variant"]),
                  QColor(COLORS["on_secondary_container"]), on)
        p.setPen(fg)
        checked = self.isChecked()
        pad = 26 if checked else 0
        p.drawText(rect.adjusted(pad, 0, 0, 0), Qt.AlignCenter, self.text())
        if checked:
            paint_icon(p, "check", QRectF(rect.left() + 11, rect.center().y() - 7, 14, 14),
                       fg, 2.2)
        p.end()


# ===========================================================================
# 卡片
# ===========================================================================

class PaperCard(QFrame):
    """M3 卡片：filled（默认）/ elevated / outlined / tonal；可选按压缩放。"""

    def __init__(self, parent=None, base: str | None = None, radius: float = 16,
                 shadow: bool = False, click_ripple: bool = False, hover_shine: bool = False,
                 variant: str = "", baked_shadow: bool = False, shadow_pad: int = 12):
        super().__init__(parent)
        self._variant = variant or ("elevated" if shadow else "filled")
        self._base = base
        self._radius = radius
        self._click_ripple = click_ripple
        self._hover_shine = hover_shine
        self._hover = 0.0
        self._ripples: list[dict] = []
        # 卡片不再有任何「阴影」实现：不用 QGraphicsDropShadowEffect（每次重绘
        # 要把整棵子树重渲一遍，实测 10ms，滚动大数字时就是卡顿源），也不用
        # 在卡片内部烘一张模糊图（那张图必须靠 16px 内缩才能装下，卡片因此
        # 比同一栏的其他卡片缩进一圈；模糊图本身还会在卡片四边渗出一圈灰边，
        # 看着像「阴影画错位置」）。层级改用 1px 描边表达：白卡 + #E7EAF1 边，
        # 位置与兄弟卡片严格对齐，零成本、零残影。
        self._baked = False
        self._spad = 0
        self._shadow_img = None
        self.setAttribute(Qt.WA_StyledBackground, False)

    def _bg(self) -> QColor:
        if self._base:
            return QColor(self._base)
        return QColor({
            "filled": COLORS["surface_container_low"],
            "elevated": COLORS["surface_container_lowest"],
            "outlined": COLORS["surface"],
            "tonal": COLORS["secondary_container"],
        }.get(self._variant, COLORS["surface_container_low"]))

    def ripple_at(self, pos: QPointF):
        if not self._click_ripple:
            return
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setDuration(460); anim.setEasingCurve(emphasized_decelerate())
        entry = {"x": pos.x(), "y": pos.y(), "anim": anim}
        anim.valueChanged.connect(lambda _: self.update())
        anim.finished.connect(lambda: self._ripples.remove(entry) if entry in self._ripples else None)
        self._ripples.append(entry); anim.start()

    def get_shine(self): return self._hover
    def set_shine(self, v):
        self._hover = v; self.update()
    shine = Property(float, get_shine, set_shine)

    def enterEvent(self, e):
        if self._hover_shine:
            a = QPropertyAnimation(self, b"shine", self)
            a.setStartValue(self._hover); a.setEndValue(1.0)
            a.setDuration(MOTION["base"]); a.setEasingCurve(standard()); a.start(); self._a = a
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._hover_shine:
            a = QPropertyAnimation(self, b"shine", self)
            a.setStartValue(self._hover); a.setEndValue(0.0)
            a.setDuration(MOTION["base"]); a.setEasingCurve(standard()); a.start(); self._a = a
        super().leaveEvent(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(self._bg())
        p.drawRoundedRect(rect, self._radius, self._radius)
        if self._hover_shine and self._hover > 0.01:
            c = QColor(COLORS["primary"]); c.setAlphaF(0.055 * self._hover)
            p.setBrush(c)
            p.drawRoundedRect(rect, self._radius, self._radius)
        # elevated / outlined 统一用 1px 描边表达层级（见 __init__ 说明）。
        # 描边取 0.5px 内缩 + 1px 笔宽：抗锯齿后正好压在像素边界上，
        # 既不会糊成两条，也不会被相邻控件的裁剪切掉一半。
        if self._variant in ("elevated", "outlined"):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(COLORS.get("card_border", "#E7EAF1")), 1.0))
            p.drawRoundedRect(rect, self._radius, self._radius)
        if self._ripples:
            p.save()
            path = QPainterPath(); path.addRoundedRect(rect, self._radius, self._radius)
            p.setClipPath(path)
            max_r = math.hypot(rect.width(), rect.height())
            for r in self._ripples:
                v = float(r["anim"].currentValue()) if r["anim"].state() else 1.0
                col = QColor(COLORS["primary"]); col.setAlphaF(max(0.0, 0.06 * (1 - v)))
                p.setPen(Qt.NoPen); p.setBrush(col)
                rr = 8 + v * max_r * 0.62
                p.drawEllipse(QPointF(r["x"], r["y"]), rr, rr)
            p.restore()
        p.end()


# ===========================================================================
# 滚轮数字
# ===========================================================================

class RollLabel(QWidget):
    """上下位移的滚轮数字；定格用轻微回弹的曲线落位。带一层柔光描边。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._cur = text
        self._prev = text
        self._t = 1.0
        self._color = QColor(COLORS["on_surface"])
        self._px = 176
        self._weight = 600
        self._glow = 0.0
        self._rolling = False
        self._pop = 0.0
        self._anim = QPropertyAnimation(self, b"roll", self)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def get_pop(self): return self._pop
    def set_pop(self, v):
        self._pop = v; self.update()
    pop = Property(float, get_pop, set_pop)

    def get_roll(self): return self._t
    def set_roll(self, v):
        self._t = v; self.update()
    roll = Property(float, get_roll, set_roll)

    def get_gscale(self): return 1.0
    def set_gscale(self, v): pass
    scale = Property(float, get_gscale, set_gscale)

    def text(self) -> str:
        return self._cur

    def setText(self, text: str):
        if text == self._cur:
            return
        self._prev = self._cur
        self._cur = text
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def set_rolling(self, on: bool):
        """抽号进行中：数字快速切换并带上下残影，像老虎机。"""
        self._rolling = bool(on)
        self.update()

    def set_fast(self, text: str, dur: int = 60):
        if text == self._cur:
            self.update()
            return
        self._prev = self._cur
        self._cur = text
        self._t = 1.0
        self.update()

    def set_now(self, text: str):
        self._anim.stop()
        self._prev = text
        self._cur = text
        self._t = 1.0
        self.update()

    def roll_to(self, text: str, dur: int = 560):
        self._prev = self._cur
        self._cur = text
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(dur)
        self._anim.setEasingCurve(QEasingCurve.OutQuint)
        self._anim.start()

    def pop_once(self, dur: int = 300):
        """直接显示（不做动画，避免崩溃）。"""
        self._pop = 0.0
        self.update()

    def set_pixel_size(self, px: int, weight: int = 600):
        self._px = max(12, int(px))
        self._weight = weight
        self.setFixedHeight(max(20, int(self._px * 1.06)))
        self.updateGeometry()
        self.update()

    def set_text_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def font(self) -> QFont:
        return display_font(self._px, self._weight)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        # 宽度按当前实际位数估算；用固定“8888”会在大号时把列宽撑爆（小窗溢出）
        txt = self._cur or self._prev or "88"
        return QSize(max(40, fm.horizontalAdvance(txt)), int(self._px * 1.06))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        rect = QRectF(self.rect())
        if self._pop > 0.01:
            c = rect.center()
            sc = 1.0 + 0.14 * self._pop
            p.translate(c)
            p.scale(sc, sc)
            p.translate(-c)
        else:
            p.setClipRect(rect)
        f = self.font()
        p.setFont(f)
        h = rect.height()
        t = max(0.0, min(1.6, self._t))

        # 滚动中：只画号码 + 两道很淡的纵向残影，避免多重曝光显脏
        if self._rolling and self._cur:
            ghost = QColor(self._color)
            ghost.setAlpha(26)
            p.setPen(ghost)
            dx = math.sin(self._t * math.pi) * 2.0
            for off in (-h * 0.07, h * 0.07):
                p.drawText(rect.translated(dx, off), Qt.AlignCenter, self._cur)
            p.setPen(self._color)
            p.drawText(rect.translated(dx, 0), Qt.AlignCenter, self._cur)
            p.end()
            return
        off_prev = -t * h * 0.92
        off_cur = (1.0 - t) * h * 0.92

        soft = QColor(self._color)
        a_prev = int(255 * max(0.0, 1.0 - t))
        a_cur = int(255 * min(1.0, max(0.0, t)))
        # 阴影透明度跟着文字一起过渡，避免上一帧残影
        if self._prev and a_prev > 4:
            soft.setAlpha(int(22 * (a_prev / 255.0)))
            p.setPen(soft)
            p.drawText(rect.translated(0, off_prev + 3), Qt.AlignCenter, self._prev)
        if self._cur and a_cur > 4:
            soft.setAlpha(int(22 * (a_cur / 255.0)))
            p.setPen(soft)
            p.drawText(rect.translated(0, off_cur + 3), Qt.AlignCenter, self._cur)
        c = self._color
        p.setPen(QColor(c.red(), c.green(), c.blue(), a_prev))
        p.drawText(rect.translated(0, off_prev), Qt.AlignCenter, self._prev)
        p.setPen(QColor(c.red(), c.green(), c.blue(), a_cur))
        p.drawText(rect.translated(0, off_cur), Qt.AlignCenter, self._cur)
        p.end()


ZoomLabel = RollLabel


def elastic_zoom(widget, start: float = 0.9, dur: int = 520):
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(1)
    return anim


def tick_pulse(widget) -> QPropertyAnimation:
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(1)
    return anim


# ===========================================================================
# 抽号反馈：光环 / 落定徽标 / 环境光
# ===========================================================================

class StampRing(QWidget):
    """落定瞬间：两圈主色光环向外扩散，透明度回收（克制，不闪）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def get_t(self): return self._t
    def set_t(self, v):
        self._t = v; self.update()
    t = Property(float, get_t, set_t)

    def fire(self, dur: int = 640):
        self.show(); self.raise_()
        a = QPropertyAnimation(self, b"t", self)
        a.setStartValue(0.0); a.setEndValue(1.0)
        a.setDuration(dur); a.setEasingCurve(emphasized_decelerate())
        a.finished.connect(self.hide)
        a.start()
        self._a = a

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        base = min(self.width(), self.height()) * 0.20
        for delay, strength in ((0.0, 1.0), (0.18, 0.55)):
            t = max(0.0, min(1.0, (self._t - delay) / (1.0 - delay)))
            if t <= 0:
                continue
            r = base + t * base * 1.9
            col = QColor(COLORS["primary"])
            col.setAlphaF(max(0.0, 0.30 * strength * (1.0 - t) ** 1.4))
            p.setPen(QPen(col, 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r, r)
        p.end()


class SealMark(QWidget):
    """抽中标记：主色圆底 + 白色对勾，弹入后常驻。"""

    def __init__(self, text: str = "中", parent=None):
        super().__init__(parent)
        self._text = text
        self._s = 0.0
        self._a = 0.0
        self.setFixedSize(46, 46)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def get_s(self): return self._s
    def set_s(self, v):
        self._s = v; self.update()
    s = Property(float, get_s, set_s)

    def get_a(self): return self._a
    def set_a(self, v):
        self._a = v; self.update()
    a = Property(float, get_a, set_a)

    def stamp(self):
        self.show(); self.raise_()
        g = QParallelAnimationGroup(self)
        a1 = QPropertyAnimation(self, b"s", self)
        a1.setStartValue(0.55); a1.setEndValue(1.0)
        a1.setDuration(MOTION["stamp"]); a1.setEasingCurve(stamp())
        a2 = QPropertyAnimation(self, b"a", self)
        a2.setStartValue(0.0); a2.setEndValue(1.0)
        a2.setDuration(180); a2.setEasingCurve(standard())
        g.addAnimation(a1); g.addAnimation(a2); g.start()
        self._g = g

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(max(0.0, min(1.0, self._a)))
        c = QPointF(self.width() / 2, self.height() / 2)
        p.translate(c); p.scale(self._s, self._s); p.translate(-c)
        side = min(self.width(), self.height()) - 4
        sq = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        rect = sq
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["primary"]))
        p.drawEllipse(rect)
        paint_icon(p, "check", rect.adjusted(12, 12, -12, -12), COLORS["on_primary"], 2.6)
        p.end()


class Halo(QWidget):
    """环境光：抽号进行中在数字背后极缓地呼吸。"""

    def __init__(self, parent=None, color: str = COLORS["primary"]):
        super().__init__(parent)
        self._power = 0.0
        self._color = color
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def get_power(self): return self._power
    def set_power(self, v):
        self._power = v; self.update()
    power = Property(float, get_power, set_power)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        if side <= 0:
            return
        a = int(max(0, min(120, 46 * self._power)))
        pm = glow_pixmap(int(side), self._color, max(6, a))
        p.setOpacity(min(1.0, 0.9 * self._power))
        p.drawPixmap(0, 0, int(side), int(side), pm)
        p.end()


def start_halo(halo: Halo):
    halo.show()
    a = QVariantAnimation(halo)
    a.setStartValue(0.35); a.setKeyValueAt(0.5, 1.0); a.setEndValue(0.35)
    a.setDuration(2600); a.setEasingCurve(QEasingCurve.InOutSine)
    a.setLoopCount(-1)
    a.valueChanged.connect(halo.set_power)
    a.start()
    halo._a = a
    return a


def stop_halo(halo: Halo):
    a = getattr(halo, "_a", None)
    if a:
        a.stop()
    halo.set_power(0.0)
    halo.hide()


def flash_halo(halo: Halo, dur: int = 640):
    halo.show()
    a = QVariantAnimation(halo)
    a.setStartValue(0.0); a.setKeyValueAt(0.22, 1.25); a.setEndValue(0.0)
    a.setDuration(dur); a.setEasingCurve(emphasized())
    a.valueChanged.connect(halo.set_power)
    a.finished.connect(lambda: (halo.set_power(0.0), halo.hide()))
    a.start()
    halo._f = a


class Badge(QWidget):
    """状态徽章：小圆点 + 文字，底色为 surface container（M3 assist chip 观感）。"""

    def __init__(self, text: str, kind: str = "neutral", parent=None):
        super().__init__(parent)
        self._text = text
        self._dot = {
            "blue": COLORS["primary"], "green": COLORS["success"],
            "pink": COLORS["error"], "camel": COLORS["camel"],
            "warm": COLORS["outline"],
        }.get(kind, COLORS["outline"])
        self.setMinimumHeight(30)
        self._pulse = 0.0

    def setText(self, text: str):
        self._text = text
        self.updateGeometry(); self.update()

    def text(self):
        return self._text

    def pulse(self, dur: int = 420):
        a = QVariantAnimation(self)
        a.setStartValue(0.0); a.setKeyValueAt(0.5, 1.0); a.setEndValue(0.0)
        a.setDuration(dur); a.setEasingCurve(standard())
        a.valueChanged.connect(lambda _: self.update())
        a.start(); self._a = a

    def sizeHint(self):
        fm = QFontMetrics(self._font())
        return QSize(fm.horizontalAdvance(self._text) + 24, 30)

    def _font(self):
        f = QFont(self.font()); f.setPixelSize(11); return f

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["surface_container_high"]))
        p.drawRoundedRect(rect, 8, 8)
        p.setBrush(QColor(self._dot))
        p.drawEllipse(QPointF(13, self.height() / 2), 3.2, 3.2)
        p.setFont(self._font())
        p.setPen(QColor(COLORS["on_surface_variant"]))
        p.drawText(rect.adjusted(21, 0, -5, 0), Qt.AlignLeft | Qt.AlignVCenter, self._text)
        p.end()


class DotDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background:{COLORS['outline_variant']}; border:none;")



class SegmentedControl(QWidget):
    """M3 segmented buttons：灰色轨道 + 白色滑块，滑动带缓动。"""

    changed = Signal(int)

    def __init__(self, labels: list[str], current: int = 0, parent=None):
        super().__init__(parent)
        self._labels = list(labels)
        self._idx = max(0, min(len(labels) - 1, current))
        self._pos = float(self._idx)
        self.setFixedHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(stamp())
        self._anim.valueChanged.connect(self._on)

    def _on(self, v):
        self._pos = float(v)
        self.update()

    def currentIndex(self):
        return self._idx

    def setCurrentIndex(self, idx: int, animate: bool = True):
        idx = max(0, min(len(self._labels) - 1, idx))
        if idx == self._idx:
            return
        self._idx = idx
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(idx))
        if animate:
            self._anim.start()
        else:
            self._pos = float(idx)
            self.update()
        self.changed.emit(idx)

    def _font(self):
        f = QFont(self.font())
        f.setPixelSize(13.5)
        f.setWeight(QFont.Medium)
        return f

    def _widths(self):
        fm = QFontMetrics(self._font())
        return [fm.horizontalAdvance(lab) + 44 for lab in self._labels]

    def sizeHint(self):
        return QSize(sum(self._widths()) + 8, 48)

    def _rects(self):
        ws = self._widths()
        x = 4.0
        out = []
        for w in ws:
            out.append(QRectF(x, 4.0, w, self.height() - 8.0))
            x += w
        return out

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["surface_container_highest"]))
        p.drawRoundedRect(rect, 24, 24)

        rects = self._rects()
        if not rects:
            return
        i0 = int(math.floor(self._pos))
        i1 = min(i0 + 1, len(rects) - 1)
        i0 = max(0, min(i0, len(rects) - 1))
        frac = self._pos - math.floor(self._pos)
        a, b = rects[i0], rects[i1]
        pill = QRectF(a.left() + (b.left() - a.left()) * frac,
                      4.0,
                      a.width() + (b.width() - a.width()) * frac,
                      self.height() - 8.0)
        p.setBrush(QColor(COLORS["surface_container_lowest"]))
        p.drawRoundedRect(pill, 20, 20)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(COLORS["outline_variant"]), 1.0))
        p.drawRoundedRect(pill.adjusted(0.4, 0.4, -0.4, -0.4), 20, 20)

        p.setFont(self._font())
        for i, r in enumerate(rects):
            sel = max(0.0, 1.0 - abs(self._pos - i))
            p.setPen(_mix(QColor(COLORS["on_surface_variant"]),
                          QColor(COLORS["on_surface"]), sel))
            p.drawText(r, Qt.AlignCenter, self._labels[i])
        p.end()

    def mousePressEvent(self, event):
        rects = self._rects()
        for i, r in enumerate(rects):
            if r.contains(event.position()):
                self.setCurrentIndex(i)
                return


# ===========================================================================
# 数字步进器（M3 segmented）
# ===========================================================================

class _BumpLabel(QLabel):
    """数字标签：弹跳只改「绘制偏移」，绝不动 widget 的 pos。

    数字由 QHBoxLayout 定位，若直接对 pos 做属性动画，连点时取到的
    pos 是上一段动画的中间值，会把它当新终点导致位置逐次累积漂移
    （数字往上/下掉出容器）。这里改用自定义属性驱动 paintEvent 偏移。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._bump = 0.0

    def get_bump(self) -> float:
        return self._bump

    def set_bump(self, v: float):
        self._bump = float(v)
        self.update()

    bump = Property(float, get_bump, set_bump)

    def paintEvent(self, event):
        if abs(self._bump) < 0.05:
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.translate(0, self._bump)
        p.setFont(self.font())
        p.setPen(QColor(COLORS["on_surface"]))
        p.drawText(self.rect(), int(self.alignment()), self.text())
        p.end()


class NumberStepper(QWidget):
    valueChanged = Signal(int)

    def __init__(self, value: int = 1, minimum: int = 1, maximum: int = 1, parent=None):
        super().__init__(parent)
        self._min = int(minimum)
        self._max = max(self._min, int(maximum))
        self._val = max(self._min, min(self._max, int(value)))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.btn_minus = IconButton("minus", self, 40)
        self.btn_plus = IconButton("plus", self, 40)
        self.value_label = _BumpLabel(str(self._val), self)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setFixedSize(58, 40)
        self.value_label.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:23px; font-weight:600;"
            "background:transparent;")
        lay.addWidget(self.btn_minus)
        lay.addWidget(self.value_label)
        lay.addWidget(self.btn_plus)
        self.setFixedHeight(48)
        self.setMinimumWidth(150)
        self.btn_minus.clicked.connect(lambda: self.setValue(self._val - 1))
        self.btn_plus.clicked.connect(lambda: self.setValue(self._val + 1))
        self._sync()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["surface_container_highest"]))
        p.drawRoundedRect(rect, 24, 24)
        p.end()

    def _sync(self):
        self.btn_minus.setEnabled(self._val > self._min)
        self.btn_plus.setEnabled(self._val < self._max)

    def value(self):
        return self._val

    def setValue(self, v: int, emit: bool = True):
        v = max(self._min, min(self._max, int(v)))
        if v == self._val:
            self._sync(); return
        self._val = v
        self.value_label.setText(str(v))
        # 连点保护：先停掉上一段动画并把绘制偏移清零，再重新弹跳。
        # 动画打在自定义 bump 属性上（只影响绘制），pos 始终由布局管理，
        # 因此无论点多少次都不会出现位置累积漂移。
        old = getattr(self, "_a", None)
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        self.value_label.set_bump(0.0)
        a = QPropertyAnimation(self.value_label, b"bump", self)
        # 幅度控制在标签内可用余量内（40 高、23px 字），OutBack 回弹也不裁字
        a.setStartValue(-4.5)
        a.setEndValue(0.0)
        a.setDuration(240); a.setEasingCurve(stamp())
        a.finished.connect(lambda: self.value_label.set_bump(0.0))
        a.start(); self._a = a
        self._sync()
        if emit:
            self.valueChanged.emit(v)

    def setMaximum(self, v: int):
        self._max = max(self._min, int(v))
        if self._val > self._max:
            self.setValue(self._max)
        else:
            self._sync()


# ===========================================================================
# 弹窗（M3 dialog：28dp 圆角、surface container high、文本按钮）
# ===========================================================================

class DialogCard(QFrame):
    def __init__(self, parent=None, radius=28):
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        # 弹窗卡沿用页面卡的材质：纯白 + 1px 描边。原来填 surface_container_high
        # （#E6E9F0）是「阴影时代」的取色 —— 那时靠投影把卡片从背景里拔出来，
        # 底色可以偏灰；去掉阴影后灰底卡片压在暗遮罩上就是一坨灰板，和页面里
        # 的白卡完全不是一套。
        p.setBrush(QColor(COLORS["surface_container_lowest"]))
        p.drawRoundedRect(rect, self._radius, self._radius)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(COLORS.get("card_border", "#E7EAF1")), 1.0))
        p.drawRoundedRect(rect, self._radius, self._radius)
        p.end()


class MaterialDialog(QDialog):
    """应用内弹窗：遮罩渐隐、卡片上浮；正文可滚动，任何缩放下按钮都可见。"""

    def __init__(self, parent=None, title: str = "", card_width: int = 440,
                 scrim_cancel: bool = True):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.scrim_cancel = scrim_cancel
        self._closing = False
        self._prepared = False
        self._card_width = card_width
        self._scrim = 0.0
        self.setWindowTitle(title or "提醒")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        self.card = DialogCard(self)
        outer.addWidget(self.card, 0, Qt.AlignCenter)

        self._card_lay = QVBoxLayout(self.card)
        self._card_lay.setContentsMargins(26, 24, 22, 16)
        self._card_lay.setSpacing(10)

        self.title_label = None
        if title:
            self.title_label = QLabel(title, self.card)
            self.title_label.setWordWrap(True)
            # 正文内容一多，QVBoxLayout 会先压标题（QLabel 默认可压到 0 高），
            # 表现为弹窗顶部只剩那条短横线。Minimum 表示「不许低于 sizeHint」。
            self.title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            self.title_label.setStyleSheet(
                f"font-size:23px; font-weight:500; color:{COLORS['on_surface']};"
                "background:transparent;")
            self._card_lay.addWidget(self.title_label)
            # 杂志式短横线：标题下 26px 的 accent 细线，所有弹窗统一
            rule = QFrame(self.card)
            rule.setFixedSize(26, 2)
            rule.setStyleSheet(f"background:{COLORS['accent_soft']}; border:none;")
            self._card_lay.addWidget(rule, 0, Qt.AlignLeft)

        self.body = QWidget()
        self.body.setObjectName("DialogBody")
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 6, 0, 2)
        self.body_lay.setSpacing(14)

        self.scroll = QScrollArea(self.card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.scroll.setWidget(self.body)
        self._card_lay.addWidget(self.scroll, 1)

        self.action_lay = QHBoxLayout()
        self.action_lay.setContentsMargins(0, 6, 0, 0)
        self.action_lay.setSpacing(4)
        self.action_lay.addStretch(1)
        self._card_lay.addLayout(self.action_lay)

    def get_scrim(self): return self._scrim
    def set_scrim(self, v):
        self._scrim = v; self.update()
    scrim = Property(float, get_scrim, set_scrim)

    def add_action(self, text: str, role: str = "none", primary: bool = False) -> RippleButton:
        b = RippleButton(text)
        b.setProperty("mtype", "filled" if primary else "text")
        b.setProperty("type", "filled" if primary else "text")
        b.setMinimumHeight(44)
        if role == "accept":
            b.clicked.connect(self.accept)
        elif role == "reject":
            b.clicked.connect(self.reject)
        self.action_lay.addWidget(b)
        return b

    def paintEvent(self, event):
        p = QPainter(self)
        c = QColor(0, 0, 0)
        c.setAlpha(int(120 * self._scrim))
        p.fillRect(self.rect(), c)
        p.end()

    def _sync_geometry(self):
        """把弹窗客户区对齐到父窗口客户区（必须在窗口 map 之前就位）。"""
        pw = self.parentWidget()
        top = pw.window() if pw is not None else None
        # 用父窗口的**客户区**对齐，而不是 frameGeometry()：
        # frameGeometry 含标题栏（实测比客户区高 31px，位置也高 31px），
        # 直接拿它 setGeometry 会让遮罩和卡片整体上移半个标题栏，
        # 弹窗里的卡片跟主窗口中心对不上。
        if top is not None:
            geo = QRect(top.mapToGlobal(QPoint(0, 0)), top.size())
        else:
            geo = QRect()
        if geo.isEmpty():
            geo = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(int(geo.x()), int(geo.y()),
                         int(geo.width()), int(geo.height()))
        return geo

    def setVisible(self, visible):
        """在窗口 map **之前**把几何和尺寸全部定好。

        原来这些全写在 showEvent 里：Qt 已经按默认位置/尺寸创建并映射了原生
        窗口，再 setGeometry 等于让分层窗口（无边框 + 透明背景）重建一次。
        实测单次 show() 从 14ms 涨到 127ms（进程内第一个弹窗能到 800ms），
        画面表现就是卡片先以错的尺寸出现、再跳到位——用户说的「抽搐」。
        """
        if visible:
            self._prepare_show()
        super().setVisible(visible)

    def show(self):
        # QWidget::show() 在 C++ 里直接调 setVisible，不会派发到 Python 的重写，
        # 所以 show / exec 这两个入口必须自己前置一次。
        self._prepare_show()
        super().show()

    def exec(self):
        self._prepare_show()
        return super().exec()

    def _prepare_show(self):
        if self._prepared:
            return
        self._closing = False
        geo = self._sync_geometry()
        avail_w = max(320, int(geo.width() * 0.9))
        avail_h = max(320, int(geo.height() * 0.86))
        self.card.setFixedWidth(min(self._card_width, avail_w))
        self.card.setMaximumHeight(avail_h)
        # 先把宽度定死并强制排一遍：折行标签的 sizeHint 依赖真实宽度，
        # 不排就拿不到准确的正文高度，show 之后还会二次收缩（又是一次跳）。
        self._card_lay.activate()
        self.body_lay.activate()
        body_need = self.body.sizeHint().height() + 30
        # 正文有多高就给多高，但不超过卡片可用高度减去标题/按钮/边距。
        # 原来固定取 avail_h*0.56：内容一多就一律截断成半屏 + 滚动条，
        # 底部的设置项（比如「管理员密码」）直接被滚出可视区。
        chrome = 150
        self.scroll.setMinimumHeight(max(56, min(body_need, int(avail_h) - chrome)))
        outer = self.layout()
        if outer is not None:
            outer.activate()          # 让卡片先拿到最终高度（居中定位才稳）
        self._card_lay.activate()
        # 首帧先把卡片设为「入场起点」：否则 show() 到 singleShot(0) 之间
        # 会以终态完整画一帧，看起来是闪一下再缩回去弹入。
        m_prepare_entry(self.card, s=0.85, dy=38)
        self._prepared = True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._prepared:
            # 兜底：万一路径没走 setVisible（子类直接 map），至少别丢尺寸
            self._prepare_show()
        QTimer.singleShot(0, self._pop_in)

    def _pop_in(self):
        if self.card.geometry().isEmpty():
            # 布局还没算出卡片几何：动画没法做，直接复位成可见，别留个隐形卡片
            m_prepare_entry(self.card, s=1.0, dy=0.0, a=1.0, bleed=0.0)
            return
        # 遮罩先铺开，卡片随后弹性落定（缩放 + 上浮 + 淡入，欠阻尼弹簧）
        s = QPropertyAnimation(self, b"scrim", self)
        s.setStartValue(min(1.0, self._scrim)); s.setEndValue(1.0)
        s.setDuration(340); s.setEasingCurve(QEasingCurve.OutQuint)
        s.start(); self._scrim_a = s

        # 卡片带着内容整体落定。**不再**给标题/正文/按钮单独叠错落动画：
        # 那会把已经显示出来的内容重置成 a=0 再重播一遍，观感是卡片出现后
        # 内容「闪一下、再一个个冒出来」——就是用户说的抽搐。
        # （实测 660ms 卡片动画结束时 title/scroll/btn 同时被置 a=0。）
        m_pop_in(self.card, dy=38, s=0.85, dur=560)

    def _fade_close(self, result: int):
        if self._closing:
            return
        self._closing = True
        s = QPropertyAnimation(self, b"scrim", self)
        s.setStartValue(self._scrim); s.setEndValue(0.0)
        s.setDuration(300); s.setEasingCurve(QEasingCurve.InCubic)
        s.start(); self._scrim_a = s
        # 卡片下沉缩小淡出；入场动画若还在跑会被内部 _stop 自动打断
        m_pop_out(self.card, dy=22, s=0.91, dur=320,
                  on_done=lambda: self._finish_close(result))

    def _finish_close(self, result: int):
        self._closing = False
        super().done(result)

    def accept(self): self._fade_close(QDialog.Accepted)
    def reject(self): self._fade_close(QDialog.Rejected)
    def done(self, result: int): self._fade_close(result)

    def mousePressEvent(self, event):
        if self.scrim_cancel and not self.card.geometry().contains(
                int(event.position().x()), int(event.position().y())):
            self.reject(); return
        super().mousePressEvent(event)


class MaterialAlert(MaterialDialog):
    def __init__(self, parent, title: str, text: str, warn: bool = False,
                 buttons: list | None = None, card_width: int = 420):
        super().__init__(parent, title, card_width=card_width, scrim_cancel=True)
        if self.title_label and warn:
            self.title_label.setStyleSheet(
                f"font-size:23px; font-weight:500; color:{COLORS['error']};"
                "background:transparent;")
        body = QLabel(text, self.body)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"font-size:14.5px; line-height:170%; color:{COLORS['on_surface_variant']};"
            "background:transparent;")
        self.body_lay.addWidget(body)
        for label, primary in (buttons or [("知道了", True)]):
            self.add_action(label, role=("accept" if primary else "reject"), primary=primary)


def ask(parent, title: str, text: str, yes: str | None = None, no: str | None = None) -> bool:
    from .lang import t
    dlg = MaterialAlert(parent, title, text,
                        buttons=[(no or t("dlg_cancel"), False), (yes or t("dlg_ok"), True)])
    return dlg.exec() == QDialog.Accepted


def inform(parent, title: str, text: str, warn: bool = False) -> None:
    from .lang import t
    dlg = MaterialAlert(parent, title, text, warn=warn, buttons=[(t("dlg_know"), True)])
    dlg.exec()


# ===========================================================================
# Snackbar / Banner
# ===========================================================================

class Snackbar(QWidget):
    HEIGHT = 50
    BOTTOM_GAP = 28

    def __init__(self, parent: QWidget, duration: int = 3200):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFixedHeight(self.HEIGHT)
        self._kind = "info"
        self._icon = "check"
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setStyleSheet(
            f"color:{COLORS['inverse_on_surface']}; font-size:13.5px; background:transparent;")
        self._duration = duration
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._slide_out)
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == event.Type.Resize and self.isVisible():
            self._place()
        return False

    def _place(self):
        p = self.parentWidget()
        w = min(max(300, self._label.sizeHint().width() + 62), p.width() - 48)
        self.setFixedWidth(w)
        self.move((p.width() - w) // 2, p.height() - self.HEIGHT - self.BOTTOM_GAP)
        self._label.setGeometry(46, 0, w - 58, self.HEIGHT)

    def show_snack(self, text: str, kind: str = "info", duration: int | None = None):
        self._kind = kind
        self._icon = {"info": "sparkle", "success": "check", "error": "close"}.get(kind, "sparkle")
        self._label.setText(text)
        self._place()
        self.show(); self.raise_()
        eff = QGraphicsOpacityEffect(self); eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        base = QPoint(self.x(), self.y())
        self.move(base.x(), base.y() + 32)
        a1 = QPropertyAnimation(eff, b"opacity", self)
        a1.setStartValue(0.0); a1.setEndValue(1.0)
        a1.setDuration(220); a1.setEasingCurve(emphasized_decelerate())
        a2 = QPropertyAnimation(self, b"pos", self)
        a2.setStartValue(self.pos()); a2.setEndValue(base)
        a2.setDuration(360); a2.setEasingCurve(stamp())
        g = QParallelAnimationGroup(self)
        g.addAnimation(a1); g.addAnimation(a2); g.start(); self._g = g
        self._timer.start(duration or self._duration)

    def _slide_out(self):
        eff = self.graphicsEffect()
        if eff is None:
            self.hide(); return
        a1 = QPropertyAnimation(eff, b"opacity", self)
        a1.setStartValue(eff.opacity()); a1.setEndValue(0.0)
        a1.setDuration(MOTION["short"]); a1.setEasingCurve(emphasized_accelerate())
        a2 = QPropertyAnimation(self, b"pos", self)
        a2.setStartValue(self.pos()); a2.setEndValue(QPoint(self.x(), self.y() + 10))
        a2.setDuration(MOTION["short"]); a2.setEasingCurve(emphasized_accelerate())
        g = QParallelAnimationGroup(self)
        g.addAnimation(a1); g.addAnimation(a2)
        g.finished.connect(self.hide); g.start(); self._g = g

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen); p.setBrush(QColor(COLORS["inverse_surface"]))
        p.drawRoundedRect(rect, 14, 14)
        col = {"info": COLORS["inverse_primary"], "success": "#9FD8B4",
               "error": "#FFB4AB"}.get(self._kind, COLORS["inverse_primary"])
        paint_icon(p, self._icon, QRectF(16, self.HEIGHT / 2 - 9, 18, 18), col, 2.0)
        p.end()


_snackbars: dict = {}


def snack(parent: QWidget | None, text: str, kind: str = "info",
          duration: int = 3200) -> None:
    host = parent.window() if parent is not None else None
    if host is None:
        return
    bar = _snackbars.get(id(host))
    if bar is None:
        bar = Snackbar(host)
        _snackbars[id(host)] = bar
    bar.raise_()
    bar.show_snack(text, kind, duration)


class Banner(QFrame):
    """M3 提示卡：tonal 底 + 图标 + 标题/正文，从上方展开淡入。"""

    def __init__(self, parent, title: str, subtitle: str = "", kind: str = "success"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._kind = kind
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(12)
        self._icon = QWidget(self)
        self._icon.setFixedSize(22, 22)
        self._icon.paintEvent = self._paint_icon  # 轻量：只画一个图标
        box = QVBoxLayout(); box.setSpacing(2)
        self.t1 = QLabel(title, self)
        self.t1.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:14.5px; font-weight:600;"
            "background:transparent;")
        self.s1 = QLabel(subtitle, self)
        self.s1.setWordWrap(True)
        self.s1.setStyleSheet(
            f"color:{COLORS['on_surface_variant']}; font-size:12.5px; background:transparent;")
        self.s1.setVisible(bool(subtitle))
        box.addWidget(self.t1); box.addWidget(self.s1)
        lay.addWidget(self._icon, 0, Qt.AlignTop)
        lay.addLayout(box, 1)
        self.hide()

    def _paint_icon(self, event):
        p = QPainter(self._icon)
        p.setRenderHint(QPainter.Antialiasing)
        col = {"success": COLORS["primary"], "info": COLORS["primary"],
               "warn": COLORS["camel"], "error": COLORS["error"]}.get(
            self._kind, COLORS["primary"])
        name = "check" if self._kind == "success" else (
            "close" if self._kind == "error" else "sparkle")
        paint_icon(p, name, QRectF(0, 0, 22, 22), col, 2.2)
        p.end()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = {"success": COLORS["primary_container"], "info": COLORS["secondary_container"],
              "warn": "#FBEAD1", "error": COLORS["error_container"]}.get(
            self._kind, COLORS["secondary_container"])
        p.setPen(Qt.NoPen); p.setBrush(QColor(bg))
        p.drawRoundedRect(rect, 14, 14)
        p.end()

    def pop(self, dur: int = 4600):
        self.show(); self.raise_()
        eff = QGraphicsOpacityEffect(self); eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        a1 = QPropertyAnimation(eff, b"opacity", self)
        a1.setStartValue(0.0); a1.setEndValue(1.0)
        a1.setDuration(280); a1.setEasingCurve(emphasized_decelerate())
        a1.finished.connect(lambda: self.setGraphicsEffect(None) if self.graphicsEffect() is eff else None)
        # 从上方滑入
        geo = self.geometry()
        self.move(geo.x(), geo.y() - 20)
        a2 = QPropertyAnimation(self, b"pos", self)
        a2.setStartValue(self.pos()); a2.setEndValue(geo.topLeft())
        a2.setDuration(360); a2.setEasingCurve(stamp())
        g = QParallelAnimationGroup(self)
        g.addAnimation(a1); g.addAnimation(a2); g.start(); self._g = g
        QTimer.singleShot(dur, self.fade_out)

    def fade_out(self):
        eff = self.graphicsEffect()
        if eff is None:
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(1.0)
            self.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setStartValue(eff.opacity()); a.setEndValue(0.0)
        a.setDuration(MOTION["short"]); a.setEasingCurve(emphasized_accelerate())
        a.finished.connect(self.hide); a.start(); self._a = a


# ===========================================================================
# M3 navigation bar：图标 + 文字 + 滑动药丸指示器
# ===========================================================================

class NavBar(QWidget):
    changed = Signal(int)
    ICONS = ("dice", "history", "chart", "tune", "shield")

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._labels = list(labels)
        self._idx = 0
        self._pos = 0.0
        self._hover = -1
        self.setFixedHeight(78)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(stamp())
        self._anim.valueChanged.connect(self._on)

    def _on(self, v):
        self._pos = float(v); self.update()

    def setCurrentIndex(self, idx: int, emit: bool = True):
        idx = max(0, min(len(self._labels) - 1, idx))
        if idx == self._idx and not self._anim.state():
            return
        self._anim.stop()
        self._anim.setStartValue(self._pos); self._anim.setEndValue(float(idx))
        self._anim.start()
        self._idx = idx
        if emit:
            self.changed.emit(idx)

    def currentIndex(self):
        return self._idx

    def setLabels(self, labels: list[str]):
        self._labels = list(labels); self.updateGeometry(); self.update()

    def _slot(self) -> float:
        return self.width() / max(1, len(self._labels))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["surface_container"]))
        p.drawRect(self.rect())
        p.setPen(QPen(QColor(COLORS["outline_variant"]), 1.0))
        p.drawLine(0, 0, w, 0)

        n = max(1, len(self._labels))
        slot = self._slot()
        pill_w, pill_h = 60.0, 30.0
        cx = slot * (self._pos + 0.5)
        cy = 10 + pill_h / 2

        p.setBrush(QColor(COLORS["primary_container"]))
        p.drawRoundedRect(QRectF(cx - pill_w / 2, cy - pill_h / 2, pill_w, pill_h),
                          pill_h / 2, pill_h / 2)

        f = QFont(self.font())
        f.setPixelSize(11.5)
        for i, label in enumerate(self._labels):
            sel = max(0.0, 1.0 - abs(self._pos - i))
            x = slot * (i + 0.5)
            icon_col = _mix(QColor(COLORS["on_surface_variant"]),
                            QColor(COLORS["on_secondary_container"]), sel)
            if self._hover == i and sel < 0.5:
                icon_col = _mix(icon_col, QColor(COLORS["on_surface"]), 0.35)
            if i < len(self.ICONS):
                sz = 24 * (getattr(self, "_icon_pulse", 1.0) if sel > 0.5 else 1.0)
                paint_icon(p, self.ICONS[i],
                           QRectF(x - sz / 2, cy - sz / 2, sz, sz), icon_col, 1.9)
            f.setWeight(QFont.Weight(600 if sel > 0.5 else 500))
            p.setFont(f)
            p.setPen(_mix(QColor(COLORS["on_surface_variant"]),
                          QColor(COLORS["on_surface"]), sel))
            p.drawText(QRectF(x - slot / 2, cy + pill_h / 2 + 6, slot, 18),
                       Qt.AlignCenter, label)
        p.end()

    def mouseMoveEvent(self, event):
        idx = int(event.position().x() // max(1.0, self._slot()))
        if idx != self._hover:
            self._hover = idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def _pulse_icon(self, idx: int):
        """切换时激活图标轻微放大再弹回。"""
        self._icon_pulse = 1.0
        a = QVariantAnimation(self)
        a.setStartValue(1.0); a.setKeyValueAt(0.4, 1.18); a.setEndValue(1.0)
        a.setDuration(320); a.setEasingCurve(stamp())
        a.valueChanged.connect(lambda v: (setattr(self, "_icon_pulse", v), self.update()))
        a.start()
        self._pulse_anim = a

    def mousePressEvent(self, event):
        n = max(1, len(self._labels))
        idx = int(event.position().x() // max(1.0, self._slot()))
        if 0 <= idx < n and idx != self._idx:
            self.setCurrentIndex(idx)


# ===========================================================================
# M3 switch
# ===========================================================================

class SwitchControl(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._on = checked
        self._t = 1.0 if checked else 0.0
        self.setFixedSize(54, 34)
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(280); self._anim.setEasingCurve(stamp())
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):
        self._t = float(v); self.update()

    def isChecked(self):
        return self._on

    def setChecked(self, v: bool, animate: bool = True):
        self._on = bool(v)
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._t)
            self._anim.setEndValue(1.0 if self._on else 0.0)
            self._anim.start()
        else:
            self._t = 1.0 if self._on else 0.0
            self.update()

    def click(self):
        self.setChecked(not self._on)
        self.toggled.emit(self._on)

    def mousePressEvent(self, event):
        self.click()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._t
        rect = QRectF(1, 3, 52, 28)
        track = _mix(QColor(COLORS["surface_container_highest"]), QColor(COLORS["primary"]), t)
        p.setPen(QPen(_mix(QColor(COLORS["outline"]), QColor(COLORS["primary"]), t), 1.2)
                  if t < 0.98 else Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, 14, 14)
        r = 8 + 2 * t
        x = 15 + t * 24
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["on_primary"] if t > 0.5 else COLORS["outline"]))
        p.drawEllipse(QPointF(x, 17), r, r)
        p.end()


# ===========================================================================
# 文件选择
# ===========================================================================

class AppFilePickerDialog(MaterialDialog):
    def __init__(self, parent, title: str = "选择文件", start_dir: str | Path | None = None,
                 suffixes: tuple = (".txt",)):
        super().__init__(parent, title, card_width=560, scrim_cancel=True)
        self._cur = Path(start_dir) if start_dir else Path.cwd()
        self._suffixes = suffixes
        self.selected_path = ""

        prow = QHBoxLayout()
        self.path_lab = QLabel("", self.body)
        self.path_lab.setStyleSheet(
            f"font-size:12px; color:{COLORS['on_surface_variant']}; background:transparent;")
        self.btn_up = IconButton("arrow_left", self.body, 38, "上一级")
        self.btn_up.clicked.connect(self._go_up)
        prow.addWidget(self.path_lab, 1)
        prow.addWidget(self.btn_up)
        self.body_lay.addLayout(prow)

        self.listw = QListWidget(self.body)
        self.listw.setMinimumHeight(320)
        self.listw.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.listw.itemDoubleClicked.connect(self._on_double)
        self.listw.itemClicked.connect(self._on_click)
        enable_touch_scroll(self.listw)
        self.body_lay.addWidget(self.listw)

        self.btn_ok = self.add_action("选择", role="none", primary=True)
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._accept_selected)
        self.add_action("取消", role="reject", primary=False)
        self._fill()

    def _fill(self):
        m_flip(self.path_lab, str(self._cur))   # 路径翻转切换
        self.listw.clear()
        try:
            entries = sorted(self._cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            self.listw.addItem("（无法访问该目录）")
            m_pop_in(self.listw.viewport(), dy=12, s=0.98, dur=380)
            return
        for e in entries:
            if e.is_dir():
                it = QListWidgetItem(f"{e.name} /")
                it.setData(Qt.UserRole, ("dir", str(e)))
            elif e.is_file() and e.suffix.lower() in self._suffixes:
                it = QListWidgetItem(e.name)
                it.setData(Qt.UserRole, ("file", str(e)))
            else:
                continue
            it.setSizeHint(QSize(0, 46))
            self.listw.addItem(it)
        if self.listw.count() == 0:
            self.listw.addItem("（没有匹配的文件）")
        m_pop_in(self.listw.viewport(), dy=12, s=0.98, dur=380)   # 目录内容弹性切换

    def _go_up(self):
        p = self._cur.parent
        if p != self._cur:
            self._cur = p; self._fill()

    def _on_double(self, item):
        data = item.data(Qt.UserRole) or ("", "")
        if data[0] == "dir":
            self._cur = Path(data[1]); self._fill()

    def _on_click(self, item):
        data = item.data(Qt.UserRole) or ("", "")
        if data[0] == "file":
            self.selected_path = data[1]
            if not self.btn_ok.isEnabled():
                self.btn_ok.setEnabled(True)
                m_bounce(self.btn_ok, s=0.88, dur=400)
                m_burst(self.btn_ok, COLORS["primary"], max_r=90, dur=520)

    def _accept_selected(self):
        if self.selected_path:
            self.accept()


# ===========================================================================
# 批量抽号：卡片逐个落定
# ===========================================================================

class TicketCard(QWidget):
    """结果卡片：M3 filled card；数字切换做交叉淡入，落定时轻微放大 + 光环。"""

    def __init__(self, num: int, name: str = "", parent=None):
        super().__init__(parent)
        self._num = num
        self._prev = num
        self._name = name
        self._scale = 1.0
        self._ring = 0.0
        self._appear = 0.0
        self._yoff = 22.0
        self._t = 1.0
        self._locked = False
        self.setFixedSize(132, 104)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._anim = QPropertyAnimation(self, b"t", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_scale(self): return self._scale
    def set_scale(self, v):
        self._scale = v; self.update()
    scale = Property(float, get_scale, set_scale)

    def get_ring(self): return self._ring
    def set_ring(self, v):
        self._ring = v; self.update()
    ring = Property(float, get_ring, set_ring)

    def get_appear(self): return self._appear
    def set_appear(self, v):
        self._appear = v; self.update()
    appear = Property(float, get_appear, set_appear)

    def get_yoff(self): return self._yoff
    def set_yoff(self, v):
        self._yoff = v; self.update()
    yoff = Property(float, get_yoff, set_yoff)

    def get_t(self): return self._t
    def set_t(self, v):
        self._t = v; self.update()
    t = Property(float, get_t, set_t)

    def set_display(self, num: int, name: str = ""):
        if num != self._num:
            self._prev = self._num
            self._num = num
            self._anim.stop()
            self._anim.setStartValue(0.0); self._anim.setEndValue(1.0)
            self._anim.start()
        self._name = name
        self.update()

    def stamp(self):
        self._locked = True
        g = QParallelAnimationGroup(self)
        a1 = QPropertyAnimation(self, b"scale", self)
        a1.setStartValue(1.35); a1.setEndValue(1.0)
        a1.setDuration(420); a1.setEasingCurve(QEasingCurve.OutBack)
        a2 = QPropertyAnimation(self, b"ring", self)
        a2.setStartValue(1.0); a2.setEndValue(0.0)
        a2.setDuration(MOTION["long2"]); a2.setEasingCurve(emphasized_decelerate())
        g.addAnimation(a1); g.addAnimation(a2); g.start()
        self._g = g

    def appear_in(self, delay: int = 0):
        def _run():
            a = QPropertyAnimation(self, b"appear", self)
            a.setStartValue(0.0); a.setEndValue(1.0)
            a.setDuration(380)
            a.setEasingCurve(emphasized_decelerate())
            b = QPropertyAnimation(self, b"yoff", self)
            b.setStartValue(32.0); b.setEndValue(0.0)
            b.setDuration(420)
            b.setEasingCurve(QEasingCurve.OutQuint)
            c = QPropertyAnimation(self, b"scale", self)
            c.setStartValue(0.82); c.setEndValue(1.0)
            c.setDuration(420)
            c.setEasingCurve(QEasingCurve.OutBack)
            g = QParallelAnimationGroup(self)
            g.addAnimation(a); g.addAnimation(b); g.addAnimation(c)
            g.start()
            self._ap = g
        if delay:
            QTimer.singleShot(delay, _run)
        else:
            _run()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setOpacity(max(0.0, min(1.0, self._appear)))
        c = QPointF(self.width() / 2, self.height() / 2 + self._yoff)
        s = self._scale * (0.92 + 0.08 * self._appear)
        p.translate(c); p.scale(s, s); p.translate(-c)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["primary_container"] if self._locked
                          else COLORS["surface_container_lowest"]))
        p.drawRoundedRect(rect, 18, 18)
        if not self._locked:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(COLORS["outline_variant"]), 1.0))
            p.drawRoundedRect(rect, 18, 18)

        num_txt = f"{self._num:02d}" if self._num < 100 else str(self._num)
        prev_txt = f"{self._prev:02d}" if self._prev < 100 else str(self._prev)
        f1 = display_font(34 if self._num < 100 else 28, 600)
        p.setFont(f1)
        col = QColor(COLORS["on_primary_container"] if self._locked else COLORS["primary"])
        t = max(0.0, min(1.0, self._t))
        if t < 0.99 and prev_txt != num_txt:
            c1 = QColor(col); c1.setAlphaF(1 - t)
            p.setPen(c1)
            p.drawText(QRectF(0, 16, self.width(), 42), Qt.AlignCenter, prev_txt)
            c2 = QColor(col); c2.setAlphaF(t)
            p.setPen(c2)
        else:
            p.setPen(col)
        p.drawText(QRectF(0, 16, self.width(), 42), Qt.AlignCenter, num_txt)

        if self._name:
            f2 = QFont(self.font()); f2.setPixelSize(12.5)
            p.setFont(f2)
            p.setPen(QColor(COLORS["on_primary_container"] if self._locked
                            else COLORS["on_surface_variant"]))
            fm = QFontMetrics(f2)
            p.drawText(QRectF(0, 66, self.width(), 22), Qt.AlignCenter,
                       fm.elidedText(self._name, Qt.ElideRight, self.width() - 20))
        p.end()


class LinearProgress(QWidget):
    """4dp 的 M3 线性进度条。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._v = 0.0
        self.setFixedHeight(4)

    def get_v(self): return self._v
    def set_v(self, v):
        self._v = v; self.update()
    v = Property(float, get_v, set_v)

    def setValue(self, pct: float, animate: bool = True):
        target = max(0.0, min(1.0, pct))
        if not animate:
            self.set_v(target); return
        a = QPropertyAnimation(self, b"v", self)
        a.setStartValue(self._v); a.setEndValue(target)
        a.setDuration(MOTION["medium"]); a.setEasingCurve(emphasized_decelerate())
        a.start(); self._a = a

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["surface_container_highest"]))
        p.drawRoundedRect(rect, 2, 2)
        if self._v > 0:
            p.setBrush(QColor(COLORS["primary"]))
            p.drawRoundedRect(QRectF(0, 0, max(6, rect.width() * self._v), rect.height()), 2, 2)
        p.end()


class BatchRevealOverlay(QWidget):
    """批量结果浮层：遮罩淡入、卡片错峰浮入、逐个落定、进度条连续推进。"""

    closed = Signal()

    def __init__(self, parent, results: list[dict], pool_nums: list[int] | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._results = list(results)
        self._pool_nums = list(pool_nums or [])
        self._cards: list[TicketCard] = []
        self._order: list[int] = []
        self._lock_idx = 0
        self._done = False
        self._scrim = 0.0
        self._flicker = QTimer(self)
        self._flicker.setInterval(70)
        self._flicker.timeout.connect(self._flick)
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._lock_next)
        self._build()
        self.hide()

    def get_scrim(self): return self._scrim
    def set_scrim(self, v):
        self._scrim = v; self.update()
    scrim = Property(float, get_scrim, set_scrim)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        self.card = PaperCard(self, radius=28, variant="elevated")
        row.addWidget(self.card, 0, Qt.AlignCenter)
        row.addStretch(1); outer.addLayout(row); outer.addStretch(1)

        v = QVBoxLayout(self.card)
        v.setContentsMargins(28, 24, 24, 18)
        v.setSpacing(14)

        head = QHBoxLayout()
        tb = QVBoxLayout(); tb.setSpacing(3)
        self.title = QLabel("本次抽中", self.card)
        self.title.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:23px; font-weight:600;"
            "background:transparent;")
        self.subtitle = QLabel("", self.card)
        self.subtitle.setStyleSheet(
            f"color:{COLORS['on_surface_variant']}; font-size:13px; background:transparent;")
        tb.addWidget(self.title); tb.addWidget(self.subtitle)
        head.addLayout(tb); head.addStretch(1)
        self.btn_skip = make_button("跳过动画", "text", min_height=42)
        self.btn_skip.clicked.connect(self.finish_all)
        head.addWidget(self.btn_skip)
        v.addLayout(head)

        self.scroll = QScrollArea(self.card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        enable_touch_scroll(self.scroll)
        self.inner = QWidget()
        self.inner.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(2, 4, 2, 4)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)

        self.bar = LinearProgress(self.card)
        v.addWidget(self.bar)

        foot = QHBoxLayout()
        self.progress = QLabel("", self.card)
        self.progress.setStyleSheet(
            f"color:{COLORS['on_surface_variant']}; font-size:12.5px; background:transparent;")
        self.btn_close = make_button("完成", "filled", min_height=44)
        self.btn_close.setMinimumWidth(104)
        self.btn_close.clicked.connect(self.close_overlay)
        foot.addWidget(self.progress); foot.addStretch(1); foot.addWidget(self.btn_close)
        v.addLayout(foot)

    # ---- 布局 ----
    def _columns(self) -> int:
        w = max(360, self.card.width())
        return max(3, min(6, (w - 40) // 142))

    def _fill_cards(self):
        cols = self._columns()
        for i, r in enumerate(self._results):
            c = TicketCard(int(r.get("num", 0)), r.get("name", "") or "", self.inner)
            self._cards.append(c)
            self.grid.addWidget(c, i // cols, i % cols)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        self.grid.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        rows = max(1, (len(self._cards) + cols - 1) // cols)
        self.inner.setMinimumHeight(rows * 112 + 10)

    # ---- 动画 ----
    def start(self):
        self._fill_cards()
        self._order = list(range(len(self._cards)))
        random.shuffle(self._order)
        n = len(self._cards)
        self.subtitle.setText(f"正在抽取 {n} 人")
        self.progress.setText(f"00 / {n:02d}")
        for i, c in enumerate(self._cards):
            c.appear_in(delay=min(320, i * 26))
            if self._pool_nums:
                c.set_display(random.choice(self._pool_nums), "")
        self._flicker.start()
        QTimer.singleShot(1250, self._begin_lock)

    def _begin_lock(self):
        self._flicker.stop()
        for i, r in enumerate(self._results):
            if i < len(self._cards):
                self._cards[i].set_display(int(r.get("num", 0)), r.get("name", "") or "")
        self.subtitle.setText("逐个揭晓")
        self._lock_idx = 0
        self._lock_next()

    def _lock_next(self):
        if self._done:
            return
        if self._lock_idx >= len(self._order):
            self._finish(); return
        self._cards[self._order[self._lock_idx]].stamp()
        self._lock_idx += 1
        n = len(self._cards)
        self.progress.setText(f"{self._lock_idx:02d} / {n:02d}")
        self.bar.setValue(self._lock_idx / max(1, n))
        # 人数少时慢慢揭晓，人多时压缩但保证整体时长
        if n <= 8:
            gap = 190
        elif n <= 14:
            gap = 150
        else:
            gap = max(72, int(1900 / max(1, n)))
        self._lock_timer.start(gap)

    def _flick(self):
        if not self._cards or not self._pool_nums:
            return
        # 所有卡片同时翻号 + 微抖，像一排老虎机
        for c in self._cards:
            if not c._locked:
                c.set_display(random.choice(self._pool_nums), "")
                c._yoff = random.uniform(-3, 3)

    def finish_all(self):
        if self._done:
            return
        self._flicker.stop(); self._lock_timer.stop()
        for i, r in enumerate(self._results):
            if i < len(self._cards):
                self._cards[i].set_display(int(r.get("num", 0)), r.get("name", "") or "")
                self._cards[i]._locked = True
                self._cards[i]._scale = 1.0
                self._cards[i]._appear = 1.0
                self._cards[i].update()
        self._finish()

    def _finish(self):
        if self._done:
            return
        self._done = True
        self.btn_skip.hide()
        self.subtitle.setText("已全部记录，点完成关闭")
        self.progress.setText(f"{len(self._cards):02d} / {len(self._cards):02d}")
        self.bar.setValue(1.0)
        self.btn_close.setFocus()

    # ---- 窗口 ----
    def showEvent(self, event):
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
            w = max(360, min(980, parent.width() - 72))
            cols = max(3, min(6, (w - 56) // 142))
            rows = max(1, (len(self._results) + cols - 1) // cols)
            h = max(280, min(parent.height() - 72, 132 + rows * 112 + 88))
            self.card.setFixedWidth(w)
            self.card.setFixedHeight(h)
        super().showEvent(event)
        a = QPropertyAnimation(self, b"scrim", self)
        a.setStartValue(0.0); a.setEndValue(1.0)
        a.setDuration(MOTION["medium"]); a.setEasingCurve(standard())
        a.start(); self._a = a
        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(0.0)
        self.card.setGraphicsEffect(eff)
        b = QPropertyAnimation(eff, b"opacity", self)
        b.setStartValue(0.0); b.setEndValue(1.0)
        b.setDuration(MOTION["medium2"]); b.setEasingCurve(standard())
        b.finished.connect(lambda: self.card.setGraphicsEffect(None))
        b.start(); self._b = b

    def resizeEvent(self, event):
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        c = QColor(0, 0, 0)
        c.setAlpha(int(140 * self._scrim))
        p.fillRect(self.rect(), c)
        p.end()

    def mousePressEvent(self, event):
        if not self._done:
            self.finish_all()

    def close_overlay(self):
        self._flicker.stop(); self._lock_timer.stop()
        a = QPropertyAnimation(self, b"scrim", self)
        a.setStartValue(self._scrim); a.setEndValue(0.0)
        a.setDuration(MOTION["short"]); a.setEasingCurve(emphasized_accelerate())

        def _gone():
            self.hide(); self.deleteLater(); self.closed.emit()
        a.finished.connect(_gone)
        a.start(); self._a = a


# ===========================================================================
# 启动标识
# ===========================================================================

class SplashWindow(QWidget):
    """主色圆标 + 柔光呼吸，随后淡出。"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 240)
        scr = QApplication.primaryScreen()
        if scr:
            c = scr.availableGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self._p = 0.0
        self._a = QVariantAnimation(self)
        self._a.setStartValue(0.0); self._a.setKeyValueAt(0.45, 1.0); self._a.setEndValue(0.0)
        self._a.setDuration(2200); self._a.setEasingCurve(QEasingCurve.InOutSine)
        self._a.setLoopCount(-1)
        self._a.valueChanged.connect(self._on)
        self._title = QLabel("随机抽号", self)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            f"color:{COLORS['on_surface']}; font-size:21px; font-weight:500;"
            "letter-spacing:4px; background:transparent;")
        self._title.setGeometry(0, 152, self.width(), 32)
        self._cap = QLabel("MATERIAL · 3", self)
        self._cap.setAlignment(Qt.AlignCenter)
        self._cap.setStyleSheet(
            f"color:{COLORS['outline']}; font-size:9px; letter-spacing:4px; background:transparent;")
        self._cap.setGeometry(0, 186, self.width(), 18)

    def _on(self, v):
        self._p = float(v); self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        c = QPointF(self.width() / 2, 90)
        p.drawPixmap(int(c.x() - 76), int(c.y() - 76), 152, 152,
                     glow_pixmap(152, COLORS["primary"], int(46 + 28 * self._p)))
        r = 34 + 2 * self._p
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["primary"]))
        p.drawEllipse(c, r, r)
        f = display_font(30, 600)
        p.setFont(f)
        p.setPen(QColor(COLORS["on_primary"]))
        p.drawText(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), Qt.AlignCenter, "抽")
        p.end()

    def show_breath(self):
        self._a.start(); self.show()
        m_pop_in(self, dy=16, s=0.78, dur=780)   # 启动标识弹性浮现

    def finish(self, dur: int = 360):
        self._a.stop()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setStartValue(1.0); a.setEndValue(0.0)
        a.setDuration(dur); a.setEasingCurve(emphasized_accelerate())
        a.finished.connect(self.close); a.start(); self._a2 = a


# ===========================================================================
# 触控 / 通用动画
# ===========================================================================

def enable_touch_scroll(scroll_area: QAbstractScrollArea) -> None:
    viewport = scroll_area.viewport()
    if scroll_area.metaObject().indexOfProperty("verticalScrollMode") >= 0:
        try:
            scroll_area.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            scroll_area.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        except Exception:
            pass
    # 触摸屏必须抓 TouchGesture，鼠标拖拽抓 LeftMouseButtonGesture；两者可共存
    viewport.setAttribute(Qt.WA_AcceptTouchEvents, True)
    try:
        QScroller.grabGesture(viewport, QScroller.ScrollerGestureType.TouchGesture)
        QScroller.grabGesture(viewport, QScroller.ScrollerGestureType.LeftMouseButtonGesture)
    except Exception:
        pass
    props = QScrollerProperties()
    SM = QScrollerProperties.ScrollMetric
    OP = QScrollerProperties.OvershootPolicy
    # 注意：DragStartDistance / velocity 的单位是【米】（Qt 内部用米制），
    # 默认 0.005m = 5mm。之前误设成 4.0（= 4 米）导致滚动完全失灵。
    props.setScrollMetric(SM.DragStartDistance, 0.005)       # 5mm
    props.setScrollMetric(SM.DragVelocitySmoothingFactor, 0.35)
    props.setScrollMetric(SM.DecelerationFactor, 0.125)      # Qt 默认，滑行自然
    props.setScrollMetric(SM.MinimumVelocity, 0.0)
    props.setScrollMetric(SM.MaximumVelocity, 3.0)           # m/s
    props.setScrollMetric(SM.MaximumClickThroughVelocity, 0.15)
    # 用标准 OutQuint 做减速曲线，不要用自定义 LUT（可能非单调导致方向异常）
    props.setScrollMetric(SM.ScrollingCurve, QEasingCurve.OutQuint)
    props.setScrollMetric(SM.HorizontalOvershootPolicy, OP.OvershootAlwaysOff)
    props.setScrollMetric(SM.VerticalOvershootPolicy, OP.OvershootAlwaysOff)
    QScroller.scroller(viewport).setScrollerProperties(props)


def enable_touch_view(view: QAbstractItemView) -> None:
    try:
        view.setAttribute(Qt.WA_AcceptTouchEvents, True)
        QScroller.grabGesture(view.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        QScroller.grabGesture(view.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
    except Exception:
        pass


def fade_slide_in(widget: QWidget, dx: float = 0, dy: float = 14, dur: int = 360,
                  delay: int = 0) -> None:
    """轻量淡入：只做透明度渐变，不挪位置。

    走 MotionEffect 通道（源位图缓存）：整页/大表淡入只在首帧渲染一次源，
    之后每帧仅一次位图合成——切页动画不再被整页重绘拖到掉帧。
    （旧实现用 QGraphicsOpacityEffect，每帧重绘整棵子树，实测切到抽号页
    单帧峰值 41~68ms、卡顿帧过半；详见 tools/frame_probe.py 前后对比。）
    """
    if getattr(widget, "_entering", False):
        return
    widget._entering = True

    def _done():
        widget._entering = False

    m_animate(widget, dur=dur, delay=delay, a0=0.0, a1=1.0,
              curve=ease_out_quint, on_done=_done)


def fade_in(widget: QWidget, dur: int = 240, delay: int = 0) -> None:
    """轻量淡入：只做透明度，不挪位置（MotionEffect 缓存通道，同上）。"""
    if getattr(widget, "_fading_in", False):
        return
    widget._fading_in = True

    def _done():
        widget._fading_in = False

    def _do():
        import shiboken6
        if not shiboken6.isValid(widget):
            widget._fading_in = False
            return
        m_animate(widget, dur=dur, a0=0.0, a1=1.0,
                  curve=ease_out_quint, on_done=_done)

    if delay > 0:
        QTimer.singleShot(delay, _do)
    else:
        _do()


# ===========================================================================
# 弹窗内通用过渡动效（只改透明度，绝不动 pos / geometry）
# ---------------------------------------------------------------------------
# 背景：NumberStepper 曾因对「布局管理的 widget」做 pos 属性动画，连点时
# 终点逐次累积漂移。这里全部走 QGraphicsOpacityEffect，布局位置永不参与
# 动画，因此任何连点/快速切换都不会产生位移漂移。
# ===========================================================================

def _opacity_effect(widget: QWidget):
    """复用/新建透明度 effect；若 widget 已被别的 effect 占用则返回 None（静默降级）。"""
    eff = widget.graphicsEffect()
    if isinstance(eff, QGraphicsOpacityEffect):
        return eff
    if eff is not None:
        return None
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    return eff


def _stop_motion(widget: QWidget, attr: str):
    """打断上一段动画并复位透明度，防止快速连点时状态叠加。"""
    old = getattr(widget, attr, None)
    if old is not None:
        try:
            old.stop()
        except Exception:
            pass
    try:
        eff = widget.graphicsEffect()
        if isinstance(eff, QGraphicsOpacityEffect):
            eff.setOpacity(1.0)
            widget.setGraphicsEffect(None)
    except Exception:
        pass


def cross_fade(widget: QWidget, on_mid, dur: int = 260,
               out_ratio: float = 0.42) -> None:
    """淡出 → 执行 on_mid()（换内容）→ 淡入。用于一次性状态切换。"""
    import shiboken6
    if not shiboken6.isValid(widget):
        return
    # 弹窗构造阶段（还没显示）的初始化不做动画，直接生效
    if not widget.isVisible():
        try:
            on_mid()
        except Exception:
            pass
        return
    attr = "_cross_a"
    _stop_motion(widget, attr)
    eff = _opacity_effect(widget)
    if eff is None:
        on_mid()
        return
    out_dur = max(60, int(dur * out_ratio))
    in_dur = max(80, dur - out_dur)
    out = QPropertyAnimation(eff, b"opacity", widget)
    out.setStartValue(eff.opacity()); out.setEndValue(0.0)
    out.setDuration(out_dur); out.setEasingCurve(QEasingCurve.InQuad)

    def _mid():
        if not shiboken6.isValid(widget):
            return
        try:
            on_mid()
        except Exception:
            pass
        inn = QPropertyAnimation(eff, b"opacity", widget)
        inn.setStartValue(0.0); inn.setEndValue(1.0)
        inn.setDuration(in_dur); inn.setEasingCurve(QEasingCurve.OutQuint)

        def _done():
            if shiboken6.isValid(widget) and widget.graphicsEffect() is eff:
                widget.setGraphicsEffect(None)

        inn.finished.connect(_done)
        inn.start()
        setattr(widget, attr, inn)

    out.finished.connect(_mid)
    out.start()
    setattr(widget, attr, out)


def swap_text(label, text: str, dur: int = 220) -> None:
    """文字变化淡出/淡入；文案相同则完全不动（高频刷新不会闪）。"""
    if label.text() == text:
        return
    cross_fade(label, lambda: label.setText(text), dur=dur)


def swap_stack_page(stack, index: int, apply_state=None, dur: int = 300) -> None:
    """QStackedWidget 步骤切换：淡出 → 切页 → 淡入。"""
    def _mid():
        if apply_state is not None:
            apply_state()
        stack.setCurrentIndex(index)

    cross_fade(stack, _mid, dur=dur)


def pulse_opacity(widget: QWidget, low: float = 0.55, dur: int = 280) -> None:
    """快速强调脉冲（1 → low → 1）：选中、成功、错误反馈。"""
    import shiboken6
    if not shiboken6.isValid(widget) or not widget.isVisible():
        return
    attr = "_pulse_a"
    _stop_motion(widget, attr)
    eff = _opacity_effect(widget)
    if eff is None:
        return
    a = QVariantAnimation(widget)
    a.setStartValue(1.0); a.setKeyValueAt(0.45, low); a.setEndValue(1.0)
    a.setDuration(dur); a.setEasingCurve(QEasingCurve.OutCubic)
    a.valueChanged.connect(lambda v: eff.setOpacity(float(v)))

    def _done():
        if not shiboken6.isValid(widget):
            return
        eff.setOpacity(1.0)
        if widget.graphicsEffect() is eff:
            widget.setGraphicsEffect(None)

    a.finished.connect(_done)
    a.start()
    setattr(widget, attr, a)


def reveal_widget(widget: QWidget, dur: int = 240) -> None:
    """从隐藏到显示：淡入（用于错误提示等条件出现的元素）。"""
    widget.setVisible(True)
    attr = "_reveal_a"
    _stop_motion(widget, attr)
    eff = _opacity_effect(widget)
    if eff is None:
        return
    eff.setOpacity(0.0)
    a = QPropertyAnimation(eff, b"opacity", widget)
    a.setStartValue(0.0); a.setEndValue(1.0)
    a.setDuration(dur); a.setEasingCurve(QEasingCurve.OutQuint)

    def _done():
        import shiboken6
        if shiboken6.isValid(widget) and widget.graphicsEffect() is eff:
            widget.setGraphicsEffect(None)

    a.finished.connect(_done)
    a.start()
    setattr(widget, attr, a)


def stagger_fade_in(widgets, dur: int = 220, gap: int = 45, delay: int = 0) -> None:
    """一组控件错落淡入（弹窗标题/按钮入场）。"""
    for i, w in enumerate(widgets):
        if w is not None:
            fade_in(w, dur=dur, delay=delay + i * gap)


def flash_item_background(item, color: QColor, dur: int = 900):
    import shiboken6
    anim = QVariantAnimation()
    anim.setStartValue(0.0); anim.setEndValue(1.0)
    anim.setDuration(dur); anim.setEasingCurve(emphasized_decelerate())

    def _set(v):
        if not shiboken6.isValid(item):
            anim.stop(); return
        c = QColor(color); c.setAlphaF(max(0.0, 0.75 * (1.0 - v)))
        item.setBackground(QBrush(c))
        # 轻微左移再回弹
        try:
            off = int(6 * (1.0 - v) * (1.0 - v))
            item.setData(Qt.UserRole + 1, off)
        except Exception:
            pass
    anim.valueChanged.connect(_set)

    def _done():
        if shiboken6.isValid(item):
            item.setBackground(QBrush())
    anim.finished.connect(_done); anim.start()
    lw = item.listWidget()
    if lw is not None:
        keep = getattr(lw, "_flash_anims", None) or []
        keep.append(anim); lw._flash_anims = keep


def animate_progress(bar: QProgressBar, value: int, dur: int = 380, delay: int = 0):
    import shiboken6

    def _do():
        if not shiboken6.isValid(bar):
            return
        a = QPropertyAnimation(bar, b"value", bar)
        a.setStartValue(0); a.setEndValue(value)
        a.setDuration(dur + int(dur * value / 100.0))
        a.setEasingCurve(emphasized_decelerate()); a.start()
        bar._a = a
    if delay > 0:
        QTimer.singleShot(delay, _do)
    else:
        _do()


class WrapLabel(QLabel):
    """自动换行 QLabel：把 heightForWidth 灌进 minimumHeight。

    QGridLayout / QVBoxLayout 都不会为 wordWrap 的 QLabel 预留多行高度
    （布局用 sizeHint，而 QLabel 的 sizeHint 按单行算），文字一旦折行就会
    画到下一行的控件上 —— 配置页「摇号池（当前可用）」压住「长期屏蔽名单」
    就是这个原因，两个 QLabel 的矩形完全相同、字叠在一起。

    这里在宽度变化/换文本后算出「当前宽度下需要多高」，写进 minimumHeight，
    布局下一轮就会把这一行撑开。pad_v 用于补上 QSS 里上下 padding 占据的
    高度（heightForWidth 不含 style padding）。
    """

    def __init__(self, text: str = "", parent=None, pad_v: int = 0):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._pad_v = max(0, int(pad_v))

    def setText(self, txt: str):
        super().setText(txt)
        self._sync_height()

    # 不在 resizeEvent 里同步：setMinimumHeight 会再触发一次 resize，
    # 宽度/行数在临界点上来回抖就会无限递归（实测直接把栈打爆）。
    # 由页面的布局落定后显式调用 fit()，一次算准。

    def _sync_height(self):
        w = self.width()
        # 宽度过小时（还没进布局）算出来的是「很多行」，会把行高永久撑大，
        # 之后即使变宽也不会自己缩回去。等真正拿到可用宽度再算。
        if w < 80:
            return
        # QLabel.heightForWidth 在 PySide6 里不可靠：实测对「42 人（…）」这种
        # 明显该折行的文本、宽度给 300 也只返回一行高度（13px）。这里直接用
        # QFontMetrics 按可用宽度排一次，行数才是真的。
        m = self.contentsMargins()          # QSS 的 padding 会同步到这里
        avail = max(20, w - m.left() - m.right())
        fm = self.fontMetrics()
        br = fm.boundingRect(QRect(0, 0, avail, 100000), int(Qt.TextWordWrap),
                             self.text() or " ")
        need = br.height() + m.top() + m.bottom() + self._pad_v
        if self.minimumHeight() != need:
            self.setMinimumHeight(need)

    def fit(self):
        """布局落定后由页面显式调用：按当前真实宽度重算高度（可增可减）。"""
        self._sync_height()


class PctBarDelegate(QStyledItemDelegate):
    """「占比」列自绘：细进度条 + 百分比。

    这一列原先用 setCellWidget 塞一个 QWidget（容器 + QProgressBar + QLabel），
    54 行就是 162 个控件；表格刷新时旧控件不会被完全回收，会以出生几何
    (0,0,169x12) 留在 viewport 左上角继续可见 —— 统计表顶部那条「3 次 / 3.6%」
    鬼影就是它们（实测 viewport 里除了 54 个正确位置的容器，还多出 54 个
    x=0 的残留控件）。

    改成 delegate 纯绘制后：零子控件、零泄漏，滚动也更省。数据放在
    item 的 Qt.UserRole 里（百分比浮点值），刷新时 restart() 重新计时。
    """

    DUR = 360        # 单行生长时长
    STAGGER = 30     # 行间错峰
    MAX_DELAY = 300  # 错峰上限

    def __init__(self, view, track: str | None = None, chunk: str | None = None,
                 text: str | None = None, pct_width: int = 52):
        super().__init__(view)
        self._view = view
        self._t0 = 0.0
        self._pct_w = pct_width
        # 条长按「占最高者的比例」而不是绝对百分比：全班 55 人时每人约 2%，
        # 绝对刻度下每根条都只有几像素，看上去像一排小圆点，读不出差距。
        self._max_pct = 0.0
        self._track = QColor(track or COLORS["line_soft"])
        self._chunk = QColor(chunk or COLORS["vermilion"])
        self._text = QColor(text or COLORS["ink_soft"])
        self._font = QFont(view.font())
        self._font.setPixelSize(12)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # ---- 动画 ----
    def restart(self, max_pct: float = 0.0):
        self._max_pct = max(0.0, float(max_pct or 0.0))
        self._t0 = time.monotonic()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        if (time.monotonic() - self._t0) * 1000 > self.MAX_DELAY + self.DUR + 40:
            self._timer.stop()
        vp = self._view.viewport()
        if vp is not None:
            vp.update()

    def _progress(self, row: int) -> float:
        el = (time.monotonic() - self._t0) * 1000 - min(row * self.STAGGER,
                                                        self.MAX_DELAY)
        if el <= 0:
            return 0.0
        if el >= self.DUR:
            return 1.0
        x = el / self.DUR
        return 1.0 - (1.0 - x) ** 3      # ease-out cubic，和主界面曲线同族

    # ---- 绘制 ----
    def paint(self, p: QPainter, opt, idx):
        super().paint(p, opt, idx)       # 样式负责背景 / 分隔线 / 选中态
        val = idx.data(Qt.UserRole)
        if val is None:
            return
        try:
            pct = float(val)
        except (TypeError, ValueError):
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRect(opt.rect)
        left = r.left() + 6
        right = r.right() - 10
        bar_w = max(0, right - left - self._pct_w - 10)
        h = 6
        cy = r.center().y() + (1 if r.height() % 2 else 0)
        track = QRectF(left, cy - h / 2, bar_w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(self._track)
        p.drawRoundedRect(track, h / 2, h / 2)
        base = self._max_pct if self._max_pct > 0.01 else 100.0
        share = max(0.0, min(1.0, pct / base))
        prog = share * self._progress(idx.row())
        if prog > 0.002:
            fill = QRectF(left, cy - h / 2, max(h, bar_w * prog), h)
            p.setBrush(self._chunk)
            p.drawRoundedRect(fill, h / 2, h / 2)
        p.setFont(self._font)
        p.setPen(self._text)
        p.drawText(QRect(right - self._pct_w, r.top(), self._pct_w, r.height()),
                   Qt.AlignRight | Qt.AlignVCenter, f"{pct:.1f}%")
        p.restore()
