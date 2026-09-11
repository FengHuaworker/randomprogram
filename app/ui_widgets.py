# -*- coding: utf-8 -*-
"""
控件层（莫兰迪 · 杂志感 · 手工感；全部动效丝滑 0.3~0.6s）：
- MaterialDialog：应用内自绘弹窗（遮罩 scrim + 圆角卡片 + 偏移装饰双线 +
  淡入 + 温和弹入/淡出动画），完全替代系统 QMessageBox / QFileDialog；
- MaterialAlert：信息/确认弹窗（ask / inform）；
- Snackbar / snack：底部轻提示；
- NavBar：带动画指示器的底部导航；
- AppFilePickerDialog：应用内文件选择器；
- RippleButton：触点涟漪 + 悬停抬升（阴影生长）/ 文字按钮下划线动画；
- PaperCard：纸面卡片 + 悬停内部高光位移 + 涟漪；
- SplashWindow：启动时莫兰迪圆形呼吸标识，之后优雅消隐；
- ZoomLabel / Halo / Badge：抽号定格、光晕、徽章呼吸。
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, Property,
                            QRectF, QPoint, QPointF, QVariantAnimation, QTimer,
                            QParallelAnimationGroup, Signal, QEvent)
from PySide6.QtGui import (QPainter, QColor, QRadialGradient, QFont, QTextOption,
                           QPen, QPainterPath, QBrush, QLinearGradient)
from PySide6.QtWidgets import (QFrame, QLabel, QPushButton, QWidget,
                               QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QProgressBar, QDialog,
                               QListWidget, QListWidgetItem, QApplication,
                               QAbstractScrollArea, QScroller, QScrollerProperties)

from . import theme
from .theme import (COLORS, STATE_HOVER, STATE_PRESS, ease_out, ease_out_quint,
                    ease_in, ease_in_out, ease_out_back, serif_style)


# ===========================================================================
# 纸面卡片：渐变底 + 噪点 + 浅描边 + 柔和阴影 + 可选涟漪/悬停高光
# ===========================================================================

class PaperCard(QFrame):
    """莫兰迪纸面卡片。
    click_ripple=True：触点水波；hover_shine=True：悬停内部高光柔移。"""

    def __init__(self, parent=None, base: str | None = None, radius=14.0, shadow=True,
                 click_ripple=False, hover_shine=False):
        super().__init__(parent)
        self._base = base
        self._radius = radius
        self._click_ripple = click_ripple
        self._hover_shine = hover_shine
        self._shine = 0.0
        self._ripples: list[dict] = []
        if shadow:
            theme.soft_shadow(self, blur=26, dy=5, alpha=38)
        if hover_shine:
            self.setMouseTracking(True)
        self.setAttribute(Qt.WA_StyledBackground, False)

    # ---- 涟漪 ----
    def ripple_at(self, pos: QPointF):
        if not self._click_ripple:
            return
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(560)
        anim.setEasingCurve(ease_out())
        entry = {"x": pos.x(), "y": pos.y(), "anim": anim}
        anim.valueChanged.connect(lambda _: self.update())
        anim.finished.connect(lambda: self._ripples.remove(entry) if entry in self._ripples else None)
        self._ripples.append(entry)
        anim.start()

    # ---- 悬停高光位移 ----
    def _shine_anim(self, target: float):
        anim = QPropertyAnimation(self, b"shine", self)
        anim.setStartValue(self._shine)
        anim.setEndValue(target)
        anim.setDuration(480)
        anim.setEasingCurve(ease_out_quint())
        anim.start()
        self._shine_anim_ref_ = anim

    def get_shine(self) -> float:
        return self._shine

    def set_shine(self, v: float) -> None:
        self._shine = v
        self.update()

    shine = Property(float, get_shine, set_shine)

    def enterEvent(self, event):
        if self._hover_shine:
            self._shine_anim(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._hover_shine:
            self._shine_anim(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        rect = QRectF(self.rect())
        theme.paint_paper(p, rect, base=self._base, radius=self._radius)
        # 悬停高光：从左侧滑向中部的柔和白光
        if self._hover_shine and self._shine > 0.01:
            p.setRenderHint(QPainter.Antialiasing)
            p.setClipRect(rect)
            cx = rect.width() * (-0.15 + 0.72 * self._shine)
            r = max(rect.width(), rect.height()) * 0.62
            g = QRadialGradient(QPointF(cx, rect.height() * 0.24), r)
            g.setColorAt(0.0, QColor(255, 255, 255, int(30 * self._shine)))
            g.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, rect.height() * 0.24), r, r)
        # 涟漪
        if self._ripples:
            p.setClipRect(rect)
            max_r = (rect.width() ** 2 + rect.height() ** 2) ** 0.5
            for r_ in self._ripples:
                anim = r_["anim"]
                v = anim.currentValue() if anim.state() else 1.0
                radius = 10 + v * max_r * 0.6
                col = QColor(COLORS["blue"])
                col.setAlphaF(max(0.0, 0.16 * (1.0 - v)))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QPointF(r_["x"], r_["y"]), radius, radius)
        p.end()


# ===========================================================================
# 涟漪按钮：悬停抬升（阴影生长）+ 文字按钮下划线动画
# ===========================================================================

class RippleButton(QPushButton):
    """带触点涟漪 + 悬停微交互的按钮。
    - 普通/主/警告按钮：悬停时阴影生长（“轻微放大并改变阴影”的温和表达）；
    - Text 按钮（ghost / action）：下划线从左到右滑入。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._ripples: list[dict] = []
        self._hover = 0.0
        self._uline = 0.0
        self._lift_effect: QGraphicsDropShadowEffect | None = None

    # ---- 悬停：阴影生长 / 下划线 ----
    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, v: float) -> None:
        self._hover = v
        if self._lift_effect is not None:
            self._lift_effect.setBlurRadius(6 + 18 * v)
            self._lift_effect.setColor(QColor(*COLORS["shadow"], int(14 + 52 * v)))
        self.update()

    hover = Property(float, get_hover, set_hover)

    def get_uline(self) -> float:
        return self._uline

    def set_uline(self, v: float) -> None:
        self._uline = v
        self.update()

    uline = Property(float, get_uline, set_uline)

    def _is_text_button(self) -> bool:
        return self.property("type") in ("ghost",) or self.property("mtype") == "action"

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._is_text_button():
            self._animate("uline", 260)
        else:
            if self._lift_effect is None and self.graphicsEffect() is None:
                self._lift_effect = theme.soft_shadow(self, blur=6, dy=2, alpha=14)
            self._animate("hover", 260)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._is_text_button():
            self._animate("uline", 300, target=0.0)   # 下划线收起（修复：移开不消失）
        else:
            self._animate("hover", 300, target=0.0)

    def _animate(self, prop: str, dur: int, target: float = 1.0):
        cur = self._hover if prop == "hover" else self._uline
        anim = QPropertyAnimation(self, prop.encode(), self)
        anim.setStartValue(cur)
        anim.setEndValue(target)
        anim.setDuration(dur)
        anim.setEasingCurve(ease_out())
        anim.start()
        setattr(self, f"_hover_anim_{prop}", anim)

    # ---- 涟漪 ----
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._spawn(event.position())

    def _spawn(self, pos: QPointF):
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(520)
        anim.setEasingCurve(ease_out())
        entry = {"x": pos.x(), "y": pos.y(), "anim": anim}
        anim.valueChanged.connect(lambda _: self.update())
        anim.finished.connect(lambda: self._ripples.remove(entry) if entry in self._ripples else None)
        self._ripples.append(entry)
        anim.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 涟漪
        if self._ripples:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 12, 12)
            p.setClipPath(path)
            max_r = (self.width() ** 2 + self.height() ** 2) ** 0.5
            for r in self._ripples:
                if not r["anim"].state():
                    continue
                v = r["anim"].currentValue()
                col = QColor(COLORS["blue_soft"])
                col.setAlphaF(max(0.0, 0.32 * (1.0 - v)))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QPointF(r["x"], r["y"]), 8 + v * max_r * 0.7, 8 + v * max_r * 0.7)
        # 文字按钮下划线（左→右滑入）
        if self._is_text_button() and self._uline > 0.01:
            fm = self.fontMetrics()
            tw = fm.horizontalAdvance(self.text())
            w = tw * self._uline
            x = (self.width() - w) / 2
            y = self.height() - 12.0
            p.setPen(Qt.NoPen)
            c = QColor(COLORS["blue_deep"])
            c.setAlpha(200)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x, y, w, 2.2), 1.1, 1.1)
        p.end()


def make_button(text: str, kind: str = "", min_height: int = 48) -> QPushButton:
    """创建按钮（自动带涟漪 + 悬停微交互）。"""
    b = RippleButton(text)
    b.setMinimumHeight(min_height)
    b.setMinimumWidth(min_height)
    if kind:
        b.setProperty("type", kind)
    b.setCursor(Qt.PointingHandCursor)
    return b


# ===========================================================================
# 弹性缩放标签（抽号定格动画载体）
# ===========================================================================

class ZoomLabel(QLabel):
    """带 scale 属性的 QLabel，缩放围绕中心进行。"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._scale = 1.0
        self._text_color = QColor(COLORS["ink"])

    def get_scale(self) -> float:
        return self._scale

    def set_scale(self, v: float) -> None:
        self._scale = v
        self.update()

    scale = Property(float, get_scale, set_scale)

    def set_text_color(self, color: str):
        self._text_color = QColor(color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        s = self._scale
        if abs(s - 1.0) > 0.0001:
            c = QPointF(self.width() / 2.0, self.height() / 2.0)
            p.translate(c)
            p.scale(s, s)
            p.translate(-c)
        p.setPen(self._text_color)
        p.setFont(self.font())
        opt = QTextOption()
        opt.setAlignment(Qt.AlignCenter)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        p.drawText(QRectF(0, 0, self.width(), self.height()), self.text(), opt)
        p.end()


def elastic_zoom(widget: ZoomLabel, start: float = 0.9, dur: int = 520) -> QPropertyAnimation:
    """定格温和放大（OutBack 轻回弹，不过分）。"""
    anim = QPropertyAnimation(widget, b"scale", widget)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setDuration(dur)
    anim.setEasingCurve(ease_out_back())
    widget._keep_anim = anim
    return anim


def tick_pulse(widget: ZoomLabel) -> QPropertyAnimation:
    """抽号滚动时每一跳的微脉冲。"""
    anim = QPropertyAnimation(widget, b"scale", widget)
    anim.setStartValue(1.06)
    anim.setEndValue(1.0)
    anim.setDuration(85)
    anim.setEasingCurve(ease_out())
    widget._tick_anim = anim
    return anim


# ===========================================================================
# 脉冲光晕
# ===========================================================================

class Halo(QWidget):
    """结果区背后的径向光晕。"""

    def __init__(self, parent=None, color: str = COLORS["blue"]):
        super().__init__(parent)
        self._power = 0.0
        self._color = QColor(color)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def get_power(self) -> float:
        return self._power

    def set_power(self, v: float) -> None:
        self._power = v
        self.update()

    power = Property(float, get_power, set_power)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = min(self.width(), self.height()) / 2.0
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        g = QRadialGradient(center, r)
        alpha = int(66 * self._power)
        col = QColor(self._color)
        g.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), alpha))
        g.setColorAt(0.72, QColor(col.red(), col.green(), col.blue(), int(alpha * 0.5)))
        g.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(center, r, r)
        p.end()


def start_halo(halo: Halo) -> QVariantAnimation:
    """呼吸光晕。"""
    halo.show()
    anim = QVariantAnimation(halo)
    anim.setStartValue(0.55)
    anim.setKeyValueAt(0.5, 0.95)
    anim.setEndValue(0.55)
    anim.setDuration(1500)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.setLoopCount(-1)
    anim.valueChanged.connect(halo.set_power)
    anim.start()
    halo._halo_anim = anim
    return anim


def stop_halo(halo: Halo) -> None:
    anim = getattr(halo, "_halo_anim", None)
    if anim:
        anim.stop()
    halo.set_power(0.0)
    halo.hide()


def flash_halo(halo: Halo, dur: int = 620) -> None:
    """定格瞬间的一次光晕爆发。"""
    halo.show()
    anim = QVariantAnimation(halo)
    anim.setStartValue(0.0)
    anim.setKeyValueAt(0.35, 1.0)
    anim.setEndValue(0.0)
    anim.setDuration(dur)
    anim.setEasingCurve(QEasingCurve.InOutCubic)
    anim.valueChanged.connect(halo.set_power)
    anim.finished.connect(lambda: (halo.set_power(0.0), halo.hide()))
    anim.start()
    halo._flash_anim = anim


# ===========================================================================
# 状态徽章
# ===========================================================================

class Badge(QLabel):
    """莫兰迪小徽章；数字变化时轻微呼吸。"""

    def __init__(self, text: str, kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        pal = {
            "blue":   ("#5E82AC", "#DCE6F0"),
            "green":  ("#6E7F66", "#E3E8DF"),
            "pink":   ("#B4717C", "#F2E0DF"),
            "camel":  ("#8A6F4E", "#EFE6D5"),
            "warm":   ("#756F66", "#E9E4DC"),
        }[kind]
        self._fg = QColor(pal[0])
        self._bg = QColor(pal[1])
        self._pulse_anim = None
        self._apply_style()
        self.setMinimumHeight(30)

    def _apply_style(self, bg: QColor | None = None):
        bg = bg or self._bg
        self.setStyleSheet(
            f"background-color:{bg.name()}; color:{self._fg.name()};"
            f"border-radius:11px; padding:4px 14px; font-size:12px; font-weight:600;")

    def pulse(self, dur: int = 420):
        if self._pulse_anim:
            self._pulse_anim.stop()
        orig = QColor(self._bg)
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(dur)
        anim.setEasingCurve(ease_out())
        anim.valueChanged.connect(lambda v: self._apply_style(orig.lighter(100 + int(10 * v))))
        anim.finished.connect(lambda: self._apply_style(orig))
        anim.start()
        self._pulse_anim = anim


class DotDivider(QFrame):
    """细渐变分隔线。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 rgba(0,0,0,0), stop:0.5 {COLORS['line']}, stop:1 rgba(0,0,0,0));")


# ===========================================================================
# 应用内弹窗（MaterialDialog 系列）
# ===========================================================================

class DialogCard(QFrame):
    """弹窗卡片：纯色表面 + 24px 圆角 + 偏移装饰双线（手工感）+ 高程阴影。"""

    def __init__(self, parent=None, radius=24.0):
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WA_StyledBackground, False)
        theme.elevation_shadow(self, blur=36, dy=8, alpha=60)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        # 偏移装饰线（手工感的错位边框）
        c_line = QColor(COLORS["camel_soft"])
        c_line.setAlpha(150)
        p.setPen(QPen(c_line, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(5, 6, 1, 1), self._radius, self._radius)
        # 表面
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["paper"]))
        p.drawRoundedRect(rect.adjusted(0, 0, -1.5, -1.5), self._radius, self._radius)
        # 顶部一条极淡的竖向渐变（微光）
        grad = QLinearGradient(rect.topLeft(), rect.topRight())
        grad.setColorAt(0.0, QColor(255, 255, 255, 46))
        grad.setColorAt(0.5, QColor(255, 255, 255, 0))
        grad.setColorAt(1.0, QColor(255, 255, 255, 46))
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(rect.left() + 2, rect.top() + 2, rect.width() - 4, 26), 12, 12)
        p.end()


class MaterialDialog(QDialog):
    """
    应用内弹窗：无边框半透明窗口盖住父窗口，自绘遮罩与居中卡片。
    弹出：遮罩淡入 + 卡片 96% -> 100%（ease-out，无夸张弹跳）；
    关闭：速淡出（accept/reject/ESC/点遮罩）。
    """

    def __init__(self, parent=None, title: str = "", card_width: int = 420,
                 scrim_cancel: bool = True):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.scrim_cancel = scrim_cancel
        self._closing = False
        self._card_width = card_width
        self.setWindowTitle(title or "提醒")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        self.card = DialogCard(self)
        outer.addWidget(self.card, 0, Qt.AlignCenter)

        self._card_lay = QVBoxLayout(self.card)
        self._card_lay.setContentsMargins(28, 26, 28, 16)
        self._card_lay.setSpacing(10)

        self.title_label = None
        if title:
            self.title_label = QLabel(title, self.card)
            self.title_label.setWordWrap(True)
            self.title_label.setStyleSheet(serif_style(21, COLORS["ink"], 600) +
                                           "; background:transparent;")
            self._card_lay.addWidget(self.title_label)

        self.body = QWidget(self.card)
        # 注意：不要在此设置任何局部 stylesheet——无选择器的 QSS 声明会被 Qt
        # 当作 QWidget 类规则，沿继承链把 QPushButton 等后代的背景也改成透明，
        # 导致按钮“隐形”（与背景融为一体）。QWidget 容器默认就是透明背景。
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 4, 0, 0)
        self.body_lay.setSpacing(12)
        self._card_lay.addWidget(self.body)

        self.action_lay = QHBoxLayout()
        self.action_lay.setContentsMargins(0, 6, 0, 4)
        self.action_lay.setSpacing(8)
        self.action_lay.addStretch(1)
        self._card_lay.addLayout(self.action_lay)

    def add_action(self, text: str, role: str = "none", primary: bool = False) -> RippleButton:
        b = RippleButton(text)
        b.setProperty("mtype", "action-primary" if primary else "action")
        b.setMinimumHeight(44)
        if role == "accept":
            b.clicked.connect(self.accept)
        elif role == "reject":
            b.clicked.connect(self.reject)
        self.action_lay.insertWidget(self.action_lay.count() - 1, b)
        return b

    # ---- 弹出 / 关闭 ----
    def paintEvent(self, event):
        """绘制遮罩（scrim）：暖黑低透明，盖住父窗口，突出弹窗卡片。"""
        p = QPainter(self)
        c = QColor(*COLORS["scrim"])
        c.setAlpha(104)
        p.fillRect(self.rect(), c)
        p.end()

    def showEvent(self, event):
        super().showEvent(event)
        # ---- 遮罩几何：必须用“顶层窗口”的屏幕坐标 ----
        # （parent 可能只是子控件，frameGeometry 是父窗口局部坐标，直接使用会错位）
        pw = self.parentWidget()
        if pw is not None:
            top = pw.window()           # 顶层窗口（QMainWindow 等）
            geo = top.frameGeometry() if top is not None else None
        else:
            geo = None
        if geo is None or geo.isEmpty():
            geo = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(int(geo.left()), int(geo.top()),
                         int(geo.width()), int(geo.height()))
        QTimer.singleShot(0, self._pop_in)

    def _pop_in(self):
        self.setWindowOpacity(0.0)
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(200)
        fade.setEasingCurve(ease_out())
        final = self.card.geometry()
        if final.isEmpty():
            return
        start = QRectF(final).adjusted(final.width() * 0.045, final.height() * 0.05,
                                       -final.width() * 0.045, -final.height() * 0.05)
        pop = QPropertyAnimation(self.card, b"geometry", self)
        pop.setStartValue(start)
        pop.setEndValue(final)
        pop.setDuration(360)
        pop.setEasingCurve(ease_out_quint())
        group = QParallelAnimationGroup(self)
        group.addAnimation(fade)
        group.addAnimation(pop)
        group.start()
        self._pop_group = group

    def _fade_close(self, result: int):
        if self._closing:
            return
        self._closing = True
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.setDuration(150)
        anim.setEasingCurve(ease_in())
        anim.finished.connect(lambda: self._finish_close(result))
        anim.start()
        self._close_anim = anim

    def _finish_close(self, result: int):
        self._closing = False
        self.setWindowOpacity(1.0)
        super().done(result)

    def accept(self):
        self._fade_close(QDialog.Accepted)

    def reject(self):
        self._fade_close(QDialog.Rejected)

    def done(self, result: int):
        self._fade_close(result)

    def mousePressEvent(self, event):
        if self.scrim_cancel and not self.card.geometry().contains(
                int(event.position().x()), int(event.position().y())):
            self.reject()
            return
        super().mousePressEvent(event)


class MaterialAlert(MaterialDialog):
    """信息 / 确认弹窗。"""

    def __init__(self, parent, title: str, text: str, warn: bool = False,
                 buttons: list | None = None, card_width: int = 400):
        super().__init__(parent, title, card_width=card_width, scrim_cancel=True)
        if self.title_label and warn:
            self.title_label.setStyleSheet(serif_style(21, COLORS["pink_dark"], 600) +
                                           "; background:transparent;")
        body = QLabel(text, self.body)
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size:15px; color:{COLORS['ink']}; background:transparent;")
        self.body_lay.addWidget(body)
        for label, primary in (buttons or [("知道了", True)]):
            self.add_action(label, role=("accept" if primary else "reject"), primary=primary)


def ask(parent, title: str, text: str, yes: str | None = None, no: str | None = None) -> bool:
    """确认弹窗（按钮文案默认走语言表）。"""
    from .lang import t
    dlg = MaterialAlert(parent, title, text,
                        buttons=[(no or t("dlg_cancel"), False), (yes or t("dlg_ok"), True)])
    return dlg.exec() == QDialog.Accepted


def inform(parent, title: str, text: str, warn: bool = False) -> None:
    """信息弹窗。warn=True 标题警示色。"""
    from .lang import t
    dlg = MaterialAlert(parent, title, text, warn=warn, buttons=[(t("dlg_know"), True)])
    dlg.exec()


# ===========================================================================
# Snackbar：底部信息卡（米白纸面 + 状态圆点 + 柔阴影，优雅滑入滑出）
# ===========================================================================

_KIND_COLORS = {
    "info": COLORS["blue_dark"],
    "success": COLORS["green_dark"],
    "error": COLORS["pink_dark"],
}


class Snackbar(QWidget):
    HEIGHT = 52
    BOTTOM_GAP = 92          # 底部导航（80 高）上方

    def __init__(self, parent: QWidget, duration: int = 3200):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFixedHeight(self.HEIGHT)
        # 纸面信息卡：柔和阴影
        theme.soft_shadow(self, blur=22, dy=4, alpha=46)
        self._dot = COLORS["blue_dark"]
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setStyleSheet(
            f"color:{COLORS['ink']}; font-size:14.5px; background:transparent;")
        self._duration = duration
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._slide_out)
        self._anim = None
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == event.Type.Resize and self.isVisible():
            self._place()
        return False

    def _place(self):
        p = self.parentWidget()
        w = min(620, p.width() - 48)
        self.setFixedWidth(w)
        self.move((p.width() - w) // 2, p.height() - self.HEIGHT - self.BOTTOM_GAP)

    def show_snack(self, text: str, kind: str = "info", duration: int | None = None):
        self._dot = _KIND_COLORS.get(kind, COLORS["blue_dark"])
        self._label.setText(text)
        # 文字左侧留出状态点位置
        self._label.setGeometry(30, 0, self.width() - 46, self.HEIGHT)
        self._place()
        self._label.setGeometry(30, 0, self.width() - 46, self.HEIGHT)
        self.show()
        self.raise_()
        self.move(self.x(), self.y() + 22)
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setStartValue(self.pos())
        anim.setEndValue(QPoint(int(self.x()), int(self.y() - 22)))
        anim.setDuration(300)
        anim.setEasingCurve(ease_out_quint())
        anim.start()
        self._anim = anim
        self._timer.start(duration or self._duration)

    def _slide_out(self):
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setStartValue(self.pos())
        anim.setEndValue(QPoint(int(self.x()), int(self.y() + 22)))
        anim.setDuration(240)
        anim.setEasingCurve(ease_in())
        anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        # 米白纸面 + 1px 暖灰描边（既有手账质感又不抢戏）
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor("#FDFBF7"))
        grad.setColorAt(1.0, QColor("#F6F1EA"))
        p.setPen(QPen(QColor(COLORS["line"]), 1.0))
        p.setBrush(grad)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), self.HEIGHT / 2, self.HEIGHT / 2)
        # 状态圆点
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._dot))
        p.drawEllipse(QPointF(18, self.HEIGHT / 2), 5, 5)
        p.end()


_snackbars: dict = {}


def snack(parent: QWidget | None, text: str, kind: str = "info",
          duration: int = 3200) -> None:
    """
    底部信息卡（同窗口复用实例）。
    kind: info（蓝）/ success（绿）/ error（粉）。
    """
    host = parent.window() if parent is not None else None
    if host is None:
        return
    bar = _snackbars.get(id(host))
    if bar is None:
        bar = Snackbar(host)
        _snackbars[id(host)] = bar
    bar.show_snack(text, kind, duration)


# ===========================================================================
# NavBar：底部导航（动画指示器）
# ===========================================================================

class NavBar(QWidget):
    """Material 3 Navigation Bar：
    高 80、激活指示器 64×32 胶囊（secondary-container）、图标 24dp + 标签 12sp，
    指示器在槽位间平滑滑动（InOutCubic）。"""

    changed = Signal(int)
    ICONS = ("draw", "list", "bars", "gear", "shield")

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._labels = labels
        self._icons = list(self.ICONS[:len(labels)])
        self._idx = 0
        self._pos = 0.0
        self.setFixedHeight(80)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(360)
        self._anim.setEasingCurve(ease_in_out())
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):
        self._pos = float(v)
        self.update()

    def setCurrentIndex(self, idx: int, emit: bool = True):
        idx = max(0, min(len(self._labels) - 1, idx))
        if idx == self._idx and not self._anim.state():
            return                      # 相同索引：静默
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(idx))
        self._anim.start()
        self._idx = idx
        if emit:
            self.changed.emit(idx)

    def currentIndex(self) -> int:
        return self._idx

    def setLabels(self, labels: list[str]):
        """更新标签（语言切换用）。"""
        self._labels = list(labels)
        self._icons = list(self.ICONS[:len(self._labels)])
        self.update()

    # ---- M3 线性图标（24dp，笔画 2px 圆头） ----
    def _draw_icon(self, p: QPainter, kind: str, cx: float, cy: float, color: QColor):
        s = 1.0
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if kind == "draw":                                   # 摇奖球
            p.drawEllipse(QPointF(0, 0), 8 * s, 8 * s)
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0, 0), 2.4, 2.4)
        elif kind == "list":                                 # 记录列表
            for i, dy in enumerate((-6, 0, 6)):
                p.drawLine(QPointF(-8, dy), QPointF(8, dy))
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(-11, -6), 1.6, 1.6)
        elif kind == "bars":                                 # 统计柱
            for i, (dx, h) in enumerate(((-7, 9), (0, 14), (7, 11))):
                p.drawLine(QPointF(dx, 8), QPointF(dx, 8 - h))
        elif kind == "gear":                                 # 设置齿轮
            p.drawEllipse(QPointF(0, 0), 6, 6)
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            import math as _m
            for k in range(6):
                ang = _m.pi / 3 * k - _m.pi / 6
                p.drawEllipse(QPointF(_m.cos(ang) * 9.5, _m.sin(ang) * 9.5), 1.7, 1.7)
        elif kind == "shield":                               # 屏蔽盾
            path = QPainterPath(QPointF(0, -9))
            path.lineTo(QPointF(8, -5))
            path.lineTo(QPointF(8, 1))
            path.quadTo(QPointF(8, 7), QPointF(0, 9))
            path.quadTo(QPointF(-8, 7), QPointF(-8, 1))
            path.lineTo(QPointF(-8, -5))
            path.closeSubpath()
            p.drawPath(path)
        p.restore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
        n = len(self._labels)
        w = self.width() / max(1, n)
        pill_w, pill_h = 64.0, 32.0
        pill_y = 14.0
        # 指示器位置随动画插值（槽位中心）
        f = self._pos
        f0 = max(0, int(f // 1)) if f >= 0 else 0
        f0 = min(f0, n - 1)
        t = f - f0
        cx0 = f0 * w + w / 2
        cx1 = min(f0 + 1, n - 1) * w + w / 2
        cx = cx0 + (cx1 - cx0) * t
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["blue_soft"]))
        p.drawRoundedRect(QRectF(cx - pill_w / 2, pill_y, pill_w, pill_h),
                          pill_h / 2, pill_h / 2)
        # 图标 + 标签（M3：icon 24dp 在指示器中，label 12sp 在下）
        for i, label in enumerate(self._labels):
            cx_i = i * w + w / 2
            sel = (i == self._idx)
            color = QColor(COLORS["blue_deep"] if sel else COLORS["ink_soft"])
            self._draw_icon(p, self._icons[i] if i < len(self._icons) else "draw",
                            cx_i, pill_y + pill_h / 2, color)
            fnt = QFont(self.font())
            fnt.setPointSizeF(11.5)
            fnt.setBold(sel)
            fnt.setFamily(self.font().family())
            p.setFont(fnt)
            p.setPen(color)
            p.drawText(QRectF(i * w, pill_y + pill_h + 4, w, 30),
                       Qt.AlignHCenter | Qt.AlignTop, label)
        p.end()

    def mousePressEvent(self, event):
        n = len(self._labels)
        w = self.width() / max(1, n)
        idx = int(event.position().x() // w)
        if 0 <= idx < n and idx != self._idx:
            self.setCurrentIndex(idx)


# ===========================================================================
# Switch：Material 开关（触控 44px+，滑块滑动动画）
# ===========================================================================

class SwitchControl(QWidget):
    """Material Switch：轨道 + 滑块，切换带动画，点击/触摸均可。"""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._on = checked
        self._t = 1.0 if checked else 0.0     # 0=关 1=开（动画值）
        self.setFixedSize(56, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(56, 32)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(ease_in_out())
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):
        self._t = float(v)
        self.update()

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, v: bool, animate: bool = True):
        self._on = bool(v)
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if self._on else 0.0)
        self._anim.start()

    def click(self):
        self.setChecked(not self._on)
        self.toggled.emit(self._on)

    def mousePressEvent(self, event):
        self.click()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._t
        # 轨道颜色：开=雾霾蓝，关=暖灰，插值
        on_c, off_c = QColor(COLORS["blue"]), QColor(COLORS["warmgray"])
        track = QColor(
            int(off_c.red() + (on_c.red() - off_c.red()) * t),
            int(off_c.green() + (on_c.green() - off_c.green()) * t),
            int(off_c.blue() + (on_c.blue() - off_c.blue()) * t))
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()),
                          self.height() / 2, self.height() / 2)
        # 滑块：白色圆，滑动 x；开启时略微放大（Material 语义）
        r = self.height() / 2 - 3
        x = r + t * (self.width() - 2 * r)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(x, self.height() / 2), r, r)
        # 开启时滑块内外影（极淡）
        if self._on:
            p.setBrush(QColor(0, 0, 0, 18))
            p.drawEllipse(QPointF(x, self.height() / 2), r + 3, r + 3)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(x, self.height() / 2), r, r)
        p.end()


# ===========================================================================
# 应用内文件选择器
# ===========================================================================

class AppFilePickerDialog(MaterialDialog):
    """应用内文件选择：浏览文件夹、只看指定后缀、双击进入/选择。"""

    def __init__(self, parent, title: str = "选择文件", start_dir: str | Path | None = None,
                 suffixes: tuple = (".txt",)):
        super().__init__(parent, title, card_width=560, scrim_cancel=True)
        self._cur = Path(start_dir) if start_dir else Path.cwd()
        self._suffixes = suffixes
        self.selected_path: str = ""

        prow = QHBoxLayout()
        self.path_lab = QLabel("", self.body)
        self.path_lab.setStyleSheet(
            f"font-size:12.5px; color:{COLORS['ink_soft']}; background:{COLORS['paper_deep']};"
            "padding:8px 12px; border-radius:8px;")
        self.btn_up = make_button("上级目录", "ghost", min_height=40)
        self.btn_up.clicked.connect(self._go_up)
        prow.addWidget(self.path_lab, 1)
        prow.addWidget(self.btn_up)
        self.body_lay.addLayout(prow)

        self.listw = QListWidget(self.body)
        self.listw.setMinimumHeight(330)
        self.listw.itemDoubleClicked.connect(self._on_double)
        self.listw.itemClicked.connect(self._on_click)
        self.body_lay.addWidget(self.listw)

        hint = QLabel(f"双击文件夹进入；点击文件后点「选择」。仅显示 {', '.join(suffixes)} 文件。",
                      self.body)
        hint.setStyleSheet(f"font-size:12px; color:{COLORS['ink_faint']}; background:transparent;")
        self.body_lay.addWidget(hint)

        self.btn_ok = self.add_action("选择", role="none", primary=True)
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._accept_selected)
        self.add_action("取消", role="reject", primary=False)

        self._fill()

    def _fill(self):
        self.path_lab.setText(str(self._cur))
        self.listw.clear()
        try:
            entries = sorted(self._cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            self.listw.addItem("（无法访问该目录）")
            return
        for e in entries:
            if e.is_dir():
                it = QListWidgetItem(f"📁  {e.name}")
                it.setData(Qt.UserRole, ("dir", str(e)))
                self.listw.addItem(it)
            elif e.is_file() and e.suffix.lower() in self._suffixes:
                it = QListWidgetItem(f"📄  {e.name}")
                it.setData(Qt.UserRole, ("file", str(e)))
                self.listw.addItem(it)
        if not entries:
            self.listw.addItem("（空目录）")

    def _go_up(self):
        p = self._cur.parent
        if p != self._cur:
            self._cur = p
            self._fill()

    def _on_double(self, item):
        kind, path = item.data(Qt.UserRole)
        if kind == "dir":
            self._cur = Path(path)
            self._fill()

    def _on_click(self, item):
        kind, path = item.data(Qt.UserRole)
        if kind == "file":
            self.selected_path = path
            self.btn_ok.setEnabled(True)

    def _accept_selected(self):
        if self.selected_path:
            self.accept()


# ===========================================================================
# SplashWindow：启动呼吸标识（莫兰迪圆形 + 细环 + 驼色小点），之后优雅消隐
# ===========================================================================

class SplashWindow(QWidget):
    """极简启动画面：圆形呼吸（scale/透明度正弦），下方衬线标题与字距拉开的英文注解，
    主窗口就绪后 opacity 渐隐关闭。"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(360, 320)
        scr = QApplication.primaryScreen()
        if scr:
            c = scr.availableGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self._phase = 0.0
        self._breath = QVariantAnimation(self)
        self._breath.setStartValue(0.0)
        self._breath.setKeyValueAt(0.5, 1.0)
        self._breath.setEndValue(0.0)
        self._breath.setDuration(2100)
        self._breath.setEasingCurve(QEasingCurve.InOutSine)
        self._breath.setLoopCount(-1)
        self._breath.valueChanged.connect(self._on_breath)
        self._title = QLabel("随机抽号", self)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(serif_style(30, COLORS["ink"], 600) +
                                  "; background:transparent;")
        self._title.move(0, 196)
        self._title.setFixedWidth(self.width())
        self._cap = QLabel("L U C K Y   D R A W", self)
        self._cap.setAlignment(Qt.AlignCenter)
        self._cap.setStyleSheet(
            f"font-family:{theme.FONT_SERIF};"
            f"color:{COLORS['camel']}; font-size:11px; letter-spacing:4px; background:transparent;")
        self._cap.move(0, 238)
        self._cap.setFixedWidth(self.width())

    def _on_breath(self, v):
        self._phase = float(v)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, 106
        s = 1.0 + 0.055 * self._phase                 # 呼吸缩放
        r = 44 * s
        # 细环（暖灰）
        p.setPen(QPen(QColor(COLORS["warmgray"]), 1.2, Qt.SolidLine))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 60, 60)
        # 主圆（雾霾蓝径向，随呼吸透明度变化）
        g = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.35), r * 1.4)
        c1 = QColor(COLORS["blue"]); c2 = QColor(COLORS["blue_dark"])
        c1.setAlphaF(0.94); c2.setAlphaF(0.92)
        g.setColorAt(0.0, c1)
        g.setColorAt(1.0, c2)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        opacity = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(2 * math.pi * self._phase))
        p.setOpacity(opacity)
        p.drawEllipse(QPointF(cx, cy), r, r)
        # 驼色小点（手工作品点缀，随呼吸微微偏移）
        p.setOpacity(0.85)
        p.setBrush(QColor(COLORS["camel"]))
        ang = math.pi * (0.75 + 0.25 * self._phase)
        p.drawEllipse(QPointF(cx + math.cos(ang) * 60, cy + math.sin(ang) * 60), 3.2, 3.2)
        p.end()

    def show_breath(self):
        self._breath.start()
        self.show()

    def finish(self, dur: int = 460):
        """优雅消隐。"""
        self._breath.stop()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(dur)
        anim.setEasingCurve(ease_in())
        anim.finished.connect(self.close)
        anim.start()
        self._fade_anim = anim


# ===========================================================================
# 动画工具：进场 / 转场 / 列表闪烁 / 进度条增长
# ===========================================================================

def enable_touch_scroll(scroll_area: QAbstractScrollArea) -> None:
    """
    触屏适配：让列表/表格/滚动区支持【拖动滚动 + 惯性滑动】。
    采用 LeftMouseButtonGesture：Windows 触屏会把触摸按压合成为鼠标事件，
    因此同一手势即可覆盖触摸拖动与鼠标拖动；滚轮、点按不受影响。
    """
    viewport = scroll_area.viewport()
    QScroller.grabGesture(viewport, QScroller.ScrollerGestureType.LeftMouseButtonGesture)
    props = QScrollerProperties()
    SM = QScrollerProperties.ScrollMetric
    OP = QScrollerProperties.OvershootPolicy
    props.setScrollMetric(SM.DragStartDistance, 12)              # 拖动判定距离（防误触）
    props.setScrollMetric(SM.DragVelocitySmoothingFactor, 0.5)   # 拖动速度平滑
    props.setScrollMetric(SM.DecelerationFactor, 0.02)           # 惯性衰减（轻手）
    props.setScrollMetric(SM.MaximumClickThroughVelocity, 24)    # 快速掠过不误触发点击
    props.setScrollMetric(SM.ScrollingCurve, theme.ease_out())
    props.setScrollMetric(SM.HorizontalOvershootPolicy, OP.OvershootAlwaysOff)
    props.setScrollMetric(SM.VerticalOvershootPolicy, OP.OvershootAlwaysOff)
    QScroller.scroller(viewport).setScrollerProperties(props)


def fade_slide_in(widget: QWidget, dx: float = 0, dy: float = 10, dur: int = 300,
                  delay: int = 0) -> None:
    """入场：淡入（无阴影特效控件）+ 从 (dx,dy) 滑回原位置（ease-out）。"""
    if getattr(widget, "_entering", False):
        return
    widget._entering = True
    has_effect = widget.graphicsEffect() is not None

    def _finish():
        if not has_effect and widget.graphicsEffect() is not None:
            widget.setGraphicsEffect(None)
        widget._entering = False

    def _do():
        eff = None
        op = None
        if not has_effect:
            eff = QGraphicsOpacityEffect(widget)
            eff.setOpacity(0.0)
            widget.setGraphicsEffect(eff)
            op = QPropertyAnimation(eff, b"opacity", widget)
            op.setStartValue(0.0)
            op.setEndValue(1.0)
            op.setDuration(dur)
            op.setEasingCurve(ease_out())
        target = QPointF(widget.pos())
        start = QPointF(target.x() + dx, target.y() + dy)
        pos = QPropertyAnimation(widget, b"pos", widget)
        pos.setStartValue(start)
        pos.setEndValue(target)
        pos.setDuration(dur)
        pos.setEasingCurve(ease_out())
        group = QParallelAnimationGroup(widget)
        if op is not None:
            group.addAnimation(op)
        group.addAnimation(pos)
        group.finished.connect(_finish)
        group.start()
        widget._enter_group = group

    if delay > 0:
        QTimer.singleShot(delay, _do)
    else:
        _do()


def fade_in(widget: QWidget, dur: int = 220, delay: int = 0) -> None:
    """仅淡入（页面转场用）。已有 graphicsEffect 的跳过。"""
    if getattr(widget, "_fading_in", False):
        return
    if widget.graphicsEffect() is not None:
        return

    def _do():
        if not widget.isVisible():
            return
        widget._fading_in = True
        eff = QGraphicsOpacityEffect(widget)
        eff.setOpacity(0.5)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setStartValue(0.5)
        anim.setEndValue(1.0)
        anim.setDuration(dur)
        anim.setEasingCurve(ease_out())

        def _done():
            if widget.graphicsEffect() is eff:
                widget.setGraphicsEffect(None)
            widget._fading_in = False
        anim.finished.connect(_done)
        anim.start()
        widget._fade_anim = anim

    if delay > 0:
        QTimer.singleShot(delay, _do)
    else:
        _do()


def flash_item_background(item, color: QColor, dur: int = 900):
    """列表项高亮闪烁（新抽中条目的“点名感”）。
    注意：QListWidgetItem 不是 QObject；列表被清空/重建时 item 会先于动画结束被删除，
    必须用 shiboken6.isValid 保护，避免在动画回调中访问已删除对象。"""
    import shiboken6
    anim = QVariantAnimation()
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(dur)
    anim.setEasingCurve(ease_out())

    def _set(v):
        if not shiboken6.isValid(item):
            anim.stop()
            return
        c = QColor(color)
        c.setAlphaF(max(0.0, 0.55 * (1.0 - v)))
        item.setBackground(QBrush(c))
    anim.valueChanged.connect(_set)

    def _done():
        if shiboken6.isValid(item):
            item.setBackground(QBrush())
    anim.finished.connect(_done)
    anim.start()
    lw = item.listWidget()
    if lw is not None:
        keep = getattr(lw, "_flash_anims", None)
        if keep is None:
            keep = []
            lw._flash_anims = keep
        keep.append(anim)


def animate_progress(bar: QProgressBar, value: int, dur: int = 380, delay: int = 0):
    """进度条从 0 增长到目标值。"""
    def _do():
        anim = QPropertyAnimation(bar, b"value", bar)
        anim.setStartValue(0)
        anim.setEndValue(value)
        anim.setDuration(dur + int(dur * value / 100.0))
        anim.setEasingCurve(ease_out())
        anim.start()
        bar._progress_anim = anim
    if delay > 0:
        QTimer.singleShot(delay, _do)
    else:
        _do()
