# -*- coding: utf-8 -*-
"""
主题层 v3：Material Design 3（种子色 = 雾霾蓝 #8BA8C7）。
=========================================================================
色板由 Google material-color-utilities 的 HCT 色调板算法生成：
  primary = P40 / onPrimary = P100 / primaryContainer = P90 / onPrimaryContainer = P10
  secondary、tertiary 同规则；neutral 生成 surface 与 surface-container 五级；
  outline = NV50，outlineVariant = NV80。
字体：全站宋体，但套用 M3 type scale（display/headline/title/body/label）。
动效：M3 standard / emphasized 曲线，100~550ms。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, QEasingCurve
from PySide6.QtGui import (QColor, QPixmap, QPainter, QBrush, QFont,
                           QPalette, QPen, QPainterPath)
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect,
                               QProxyStyle, QStyle)

# ---------------------------------------------------------------------------
# 一、M3 色彩角色
# ---------------------------------------------------------------------------

COLORS = {
    "primary": "#4A6077",
    "on_primary": "#FFFFFF",
    "primary_container": "#CFE4F7",
    "on_primary_container": "#0A1E2E",
    "secondary": "#57606B",
    "on_secondary": "#FFFFFF",
    "secondary_container": "#DCE4EE",
    "on_secondary_container": "#161E27",
    "tertiary": "#5F5C70",
    "on_tertiary": "#FFFFFF",
    "tertiary_container": "#E5DFF2",
    "on_tertiary_container": "#1B1828",
    "error": "#BA1A1A",
    "on_error": "#FFFFFF",
    "error_container": "#FFDAD6",
    "on_error_container": "#410002",
    "surface": "#F1F3F8",
    "surface_dim": "#DADADD",
    "surface_bright": "#FCFCFF",
    "surface_container_lowest": "#FFFFFF",
    "surface_container_low": "#F8F9FC",
    "surface_container": "#EBEDF3",
    "surface_container_high": "#E6E9F0",
    "surface_container_highest": "#E0E4EC",
    "on_surface": "#1A1C1E",
    "on_surface_variant": "#43474D",
    "outline": "#73777D",
    "outline_variant": "#C3C7CD",
    "inverse_surface": "#2F3033",
    "inverse_on_surface": "#F1F0F4",
    "inverse_primary": "#B1C9E3",
    "surface_tint": "#30628C",
    "scrim": (0, 0, 0),
    "shadow": (0, 0, 0),
    # 自定义语义色
    "success": "#4B6A58",
    "on_success": "#FFFFFF",
    "success_container": "#D9E6DE",
    "on_success_container": "#11201A",
    # 杂志感强调色：比 primary 更浅，用于大数字、章节号、细线
    "accent": "#5E7890",
    "btn_ink": "#6B8CA6",       # 主按钮：比 accent 亮、比 primary 柔，杂志感雾霾蓝
    "accent_soft": "#A9BCCD",
    "accent_wash": "#E8EFF6",
    # 卡片描边：代替阴影表达层级。比 outline_variant 淡、比底色深，
    # 在 #F1F3F8 底上刚好勾出白卡轮廓，不会显得发黑。
    "card_border": "#DCE1EB",
}

# 旧键名别名（历史页面仍引用）
COLORS.update({
    "blue": COLORS["primary"],
    "blue_dark": "#3F5468",
    "blue_deep": COLORS["on_primary_container"],
    "blue_soft": COLORS["primary_container"],
    "pink": COLORS["error"],
    "pink_dark": COLORS["error"],
    "green": COLORS["success"],
    "green_dark": COLORS["success"],
    "green_soft": COLORS["success_container"],
    "warmgray": COLORS["outline_variant"],
    "cream": COLORS["surface"],
    "paper": COLORS["surface"],
    "paper_deep": COLORS["surface_container_low"],
    "surface_low": COLORS["surface_container_low"],
    "surface_high": COLORS["surface_container_high"],
    "surface_highest": COLORS["surface_container_highest"],
    "surface_lowest": COLORS["surface_container_lowest"],
    "camel": "#7A5A2E",
    "camel_soft": "#F3E2C7",
    "camel_deep": "#4A340F",
    "ink": COLORS["on_surface"],
    "ink_soft": COLORS["on_surface_variant"],
    "ink_faint": COLORS["outline"],
    "line": COLORS["outline_variant"],
    "line_soft": COLORS["surface_container_high"],
    "rule": COLORS["outline_variant"],
    "rule_soft": COLORS["surface_container_high"],
    "vermilion": COLORS["primary"],
    "vermilion_dark": "#3F5468",
    "vermilion_soft": COLORS["primary_container"],
})

STATE_HOVER = "#EDEFF3"
STATE_PRESS = "#E4E7EC"
STATE_PRIMARY_HOVER = "#556C84"
STATE_PRIMARY_PRESS = "#3F5468"
STATE_TONAL_HOVER = "#D2DCE8"
STATE_TONAL_PRESS = "#C7D3E1"

SHAPE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "xxl": 28, "full": 999}
ELEV = {0: (0, 0, 0), 1: (8, 2, 18), 2: (14, 3, 28), 3: (22, 6, 40), 4: (30, 8, 54), 5: (38, 10, 70)}

# ---------------------------------------------------------------------------
# 二、字体与 M3 type scale（宋体）
# ---------------------------------------------------------------------------

FONT_SANS = '"SimSun"'
_SCALE = 1.0  # 全局缩放系数，由窗口尺寸驱动

def scale() -> float:
    return _SCALE

def set_scale(v: float):
    global _SCALE
    _SCALE = max(0.7, min(2.5, v))

def sp(px: float) -> int:
    """按缩放系数换算像素值。"""
    return max(1, int(round(px * _SCALE)))
FONT_SERIF = '"SimSun"'
FONT_DISPLAY = '"SimSun"'
_SANS_CANDIDATES = ("SimSun", "宋体", "NSimSun", "Microsoft YaHei UI", "SimHei")

TYPE_SCALE = {
    "display_large": (57, 64, 400, -0.25),
    "display_medium": (45, 52, 400, 0.0),
    "display_small": (36, 44, 400, 0.0),
    "headline_large": (32, 40, 400, 0.0),
    "headline_medium": (28, 36, 400, 0.0),
    "headline_small": (24, 32, 400, 0.0),
    "title_large": (22, 28, 400, 0.0),
    "title_medium": (16, 24, 500, 0.15),
    "title_small": (14, 20, 500, 0.1),
    "body_large": (16, 24, 400, 0.5),
    "body_medium": (14, 20, 400, 0.25),
    "body_small": (12, 16, 400, 0.4),
    "label_large": (14, 20, 500, 0.1),
    "label_medium": (12, 16, 500, 0.5),
    "label_small": (11, 16, 500, 0.5),
}


def register_fonts(base_dir) -> None:
    import os
    import sys
    from PySide6.QtGui import QFontDatabase
    for cand in (getattr(sys, "_MEIPASS", None), base_dir):
        if not cand:
            continue
        p = f"{cand}/assets/fonts"
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.lower().endswith((".ttf", ".otf")):
                    try:
                        QFontDatabase.addApplicationFont(os.path.join(p, fn))
                    except Exception:
                        pass
            return


def _first_available(candidates) -> str:
    from PySide6.QtGui import QFontDatabase
    try:
        fams = set(QFontDatabase.families())
    except Exception:
        fams = set()
    for cand in candidates:
        if cand in fams:
            return cand
    return candidates[-1]


def pick_font_family() -> tuple[str, str]:
    sans = _first_available(_SANS_CANDIDATES)
    return sans, sans


# ---------------------------------------------------------------------------
# 三、动效令牌
# ---------------------------------------------------------------------------

MOTION = {
    "instant": 100, "quick": 150, "short": 200, "base": 250,
    "medium": 300, "slow": 350, "stage": 400, "long": 500, "stamp": 550,
    "short1": 100, "short2": 150, "short3": 200, "short4": 250,
    "medium1": 300, "medium2": 350, "medium3": 400,
    "long1": 500, "long2": 550,
}

_curve_cache: dict = {}


def bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    key = (round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))
    if key in _curve_cache:
        return _curve_cache[key]
    table = [0.0] * 256

    def cubic(a, b, u):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3

    pts = []
    prev_x = -1.0
    for i in range(257):
        u = i / 256
        x = cubic(x1, x2, u)
        y = cubic(y1, y2, u)
        if x < 0 or x > 1 or x < prev_x:
            continue
        prev_x = x
        pts.append((x, y))
    j = 1
    for k in range(256):
        target = k / 255.0
        y = target
        while j < len(pts) and pts[j][0] < target:
            j += 1
        if j < len(pts):
            (xa, ya), (xb, yb) = pts[j - 1], pts[j]
            span = (xb - xa) or 1e-9
            y = ya + (yb - ya) * (target - xa) / span
        table[k] = y

    def fn(progress: float) -> float:
        x = min(max(progress, 0.0), 1.0)
        idx = int(x * 255)
        lo = table[idx]
        hi = table[min(idx + 1, 255)]
        return lo + (hi - lo) * (x * 255 - idx)

    curve = QEasingCurve(QEasingCurve.Custom)
    curve.setCustomType(fn)
    _curve_cache[key] = curve
    return curve


def standard() -> QEasingCurve:              return QEasingCurve.OutCubic
def standard_decelerate() -> QEasingCurve:   return QEasingCurve.OutQuint
def emphasized() -> QEasingCurve:            return QEasingCurve.OutCubic
def emphasized_decelerate() -> QEasingCurve: return QEasingCurve.OutQuint
def emphasized_accelerate() -> QEasingCurve: return QEasingCurve.InQuint
def stamp() -> QEasingCurve:                 return QEasingCurve.OutBack


def ease_out() -> QEasingCurve:        return emphasized_decelerate()
def ease_out_quint() -> QEasingCurve:  return emphasized_decelerate()
def ease_in_out() -> QEasingCurve:     return standard()
def ease_in() -> QEasingCurve:         return emphasized_accelerate()
def ease_out_back() -> QEasingCurve:   return stamp()
def spring() -> QEasingCurve:          return stamp()


# ---------------------------------------------------------------------------
# 四、全局 QSS（M3 组件）
# ---------------------------------------------------------------------------

def build_qss() -> str:
    c = COLORS
    return f"""
* {{ font-family: {FONT_SANS}; outline: none; }}
QMainWindow, QDialog {{ background-color: {c['surface']}; }}
QWidget#RootSurface {{ background-color: {c['surface']}; }}
QWidget#DialogBody {{ background: transparent; }}

#TopBar {{ background: {c['surface']}; border: none; }}
#AppTitle {{ color: {c['on_surface']}; font-size: {sp(21)}px; font-weight: 600; }}
QFrame#ClassChip {{
    background: {c['surface_container_high']};
    border-radius: 20px;
}}
QComboBox#ClassCombo {{
    background: transparent; border: none; padding: 0;
    min-height: 32px; font-size: {sp(14)}px; font-weight: 500; color: {c['on_surface']};
}}
QComboBox#ClassCombo::drop-down {{ width: 0px; border: none; background: transparent; }}
QComboBox#ClassCombo::down-arrow {{ image: none; width: 0px; height: 0px; }}
#AppCaption {{ color: {c['on_surface_variant']}; font-size: {sp(11)}px; font-weight: 400; }}
#ModeBadge {{
    background: {c['secondary_container']}; color: {c['on_secondary_container']};
    border-radius: 8px; padding: 6px 12px; font-size: {sp(12)}px; font-weight: 500;
}}

QPushButton {{
    background: transparent; color: {c['primary']};
    border: 1px solid {c['outline']}; border-radius: 20px;
    padding: 0 24px; min-height: {sp(40)}px; font-size: {sp(14)}px; font-weight: 500;
}}
QPushButton:hover {{ background: {STATE_HOVER}; }}
QPushButton:pressed {{ background: {STATE_PRESS}; }}
QPushButton:disabled {{ color: {c['on_surface']}; border-color: {c['outline_variant']}; }}
QPushButton[type="filled"] {{
    background: {c['btn_ink']}; color: #FFFFFF; border: none;
    border-radius: {sp(24)}px; font-size: {sp(14)}px; font-weight: 500; padding: 0 {sp(28)}px;
    min-height: {sp(52)}px;
}}
QPushButton[type="filled"]:hover {{ background: {STATE_PRIMARY_HOVER}; }}
QPushButton[type="filled"]:pressed {{ background: {STATE_PRIMARY_PRESS}; }}
QPushButton[type="filled"]:disabled {{
    background: {c['surface_container_highest']}; color: {c['on_surface']};
}}
QPushButton[type="tonal"] {{
    background: {c['secondary_container']}; color: {c['on_secondary_container']};
    border: none; border-radius: 20px; font-weight: 500;
}}
QPushButton[type="tonal"]:hover {{ background: {STATE_TONAL_HOVER}; }}
QPushButton[type="tonal"]:pressed {{ background: {STATE_TONAL_PRESS}; }}
QPushButton[type="danger"] {{
    background: {c['error_container']}; color: {c['on_error_container']};
    border: none; border-radius: 20px; font-weight: 500;
}}
QPushButton[type="error"] {{
    background: {c['error']}; color: {c['on_error']}; border: none;
    border-radius: 20px; font-weight: 500;
}}
QPushButton[type="error"]:hover {{ background: #9E1616; }}
QPushButton[type="text"] {{
    background: transparent; color: {c['primary']}; border: none;
    border-radius: 20px; padding: 0 18px; min-height: {sp(40)}px;
}}
QPushButton[type="text"]:hover {{ background: {STATE_HOVER}; }}
QPushButton[type="text"]:pressed {{ background: {STATE_PRESS}; }}
QPushButton[type="ghost"] {{
    background: transparent; border: none; color: {c['primary']};
    border-radius: 20px; padding: 0 16px; min-height: {sp(40)}px;
    font-size: {sp(14)}px; font-weight: 500;
}}
QPushButton[type="ghost"]:hover {{ background: {STATE_HOVER}; }}
QPushButton[type="fab"] {{
    background: {c['primary_container']}; color: {c['on_primary_container']};
    border: none; border-radius: 16px; font-size: {sp(16)}px; font-weight: 500;
    padding: 0 24px;
}}
QPushButton[type="fab"]:hover {{ background: {c['primary']}; color: {c['on_primary']}; }}
QPushButton[type="fab"]:disabled {{
    background: {c['surface_container_highest']}; color: {c['outline']};
}}
QPushButton[mtype="action"] {{
    background: transparent; border: none; color: {c['primary']};
    border-radius: 20px; min-height: {sp(40)}px; padding: 0 18px; font-weight: 500;
}}
QPushButton[mtype="action"]:hover {{ background: {STATE_HOVER}; }}
QPushButton[mtype="action-primary"] {{
    background: {c['primary']}; border: none; color: {c['on_primary']};
    border-radius: 20px; min-height: {sp(40)}px; padding: 0 20px; font-weight: 500;
}}
QPushButton[mtype="action-primary"]:hover {{ background: {STATE_PRIMARY_HOVER}; }}

QLineEdit, QSpinBox, QComboBox, QDateTimeEdit, QDateEdit, QTimeEdit {{
    background: {c['surface_container_highest']}; color: {c['on_surface']};
    border: none; border-bottom: 1px solid {c['on_surface_variant']};
    border-radius: 8px 8px 0 0; padding: 0 16px; min-height: {sp(52)}px;
    font-size: {sp(16)}px;
    selection-background-color: {c['primary_container']};
    selection-color: {c['on_primary_container']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
QDateTimeEdit:focus, QDateEdit:focus, QTimeEdit:focus {{
    border-bottom: 2px solid {c['primary']}; padding: 0 15px;
}}
QLineEdit:disabled, QSpinBox:disabled {{
    color: {c['outline']}; background: {c['surface_container']};
    border-bottom-color: {c['outline_variant']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
    background: transparent; border: none; width: 26px;
}}
QDateTimeEdit::drop-down {{
    width: 34px; border: none; background: transparent;
}}
QDateTimeEdit {{ padding-right: 40px; }}
QComboBox::drop-down {{ border: none; width: 36px; background: transparent; }}
QComboBox QAbstractItemView {{
    background: {c['surface_container_low']}; color: {c['on_surface']};
    border: 1px solid {c['outline_variant']}; border-radius: 8px; padding: 4px;
    selection-background-color: {c['secondary_container']};
    selection-color: {c['on_secondary_container']};
}}
QComboBox QAbstractItemView::item {{
    min-height: 46px; padding: 0 14px; border-radius: 8px; margin: 1px 4px;
}}

QTableWidget, QListWidget {{
    background: transparent; alternate-background-color: transparent;
    border: none; color: {c['on_surface']}; font-size: {sp(13.5)}px;
    gridline-color: {c['outline_variant']};
    selection-background-color: {c['secondary_container']};
}}
QTableWidget::item {{
    padding: 10px 14px; border-bottom: 1px solid {c['outline_variant']};
    color: {c['on_surface']};
}}
QTableWidget::item:hover {{ background: {c['surface_container_low']}; }}
QTableWidget::item:selected, QListWidget::item:selected {{
    background: {c['secondary_container']}; color: {c['on_secondary_container']};
}}
QListWidget::item {{
    padding: 11px 12px; border: none; border-radius: 8px; margin: 1px 0;
    color: {c['on_surface']};
}}
QListWidget::item:hover {{ background: {c['surface_container_low']}; }}
QListWidget::item:selected {{
    background: {c['secondary_container']}; color: {c['on_secondary_container']};
}}
QListWidget::item:hover {{ background: {STATE_HOVER}; }}
QHeaderView::section {{
    background: transparent; color: {c['on_surface_variant']};
    border: none; border-bottom: 1px solid {c['outline_variant']};
    padding: 12px 14px; font-size: {sp(11)}px; font-weight: 600; letter-spacing: 1.2px;
}}
QTableCornerButton::section {{ background: {c['surface_container_low']}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 3px 2px; }}
QScrollBar::handle:vertical {{
    background: {c['accent_soft']}; border-radius: 4px; min-height: {sp(44)}px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px 3px; }}
QScrollBar::handle:horizontal {{
    background: {c['accent_soft']}; border-radius: 4px; min-width: 44px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QCheckBox, QRadioButton {{
    color: {c['on_surface']}; font-size: {sp(14)}px; spacing: {sp(12)}px; min-height: {sp(44)}px;
}}

QToolTip {{
    background: {c['inverse_surface']}; color: {c['inverse_on_surface']};
    border: none; padding: 8px 12px; font-size: {sp(12)}px; border-radius: 4px;
}}
QMenu {{
    background: {c['surface_container_lowest']}; border: 1px solid {c['outline_variant']};
    border-radius: 12px; padding: 8px;
}}
QMenu::item {{
    padding: 10px 24px; min-height: {sp(40)}px; font-size: {sp(14)}px;
    color: {c['on_surface']}; border-radius: 8px;
}}
QMenu::item:selected {{ background: {c['secondary_container']}; }}

QCalendarWidget QWidget {{ background: {c['surface']}; color: {c['on_surface']}; }}
QCalendarWidget QAbstractItemView:enabled {{
    background: {c['surface']}; selection-background-color: {c['primary']};
    selection-color: {c['on_primary']};
}}
"""


# ---------------------------------------------------------------------------
# 五、绘制与字体工具
# ---------------------------------------------------------------------------

def paper_texture() -> QPixmap:
    pm = QPixmap(1, 1)
    pm.fill(Qt.transparent)
    return pm


def paint_paper(painter: QPainter, rect: QRectF, base: str | None = None,
                radius: float = 12.0, border: bool = False) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(base or COLORS["surface_container_low"])))
    painter.drawRoundedRect(rect, radius, radius)
    if border:
        painter.setPen(QPen(QColor(COLORS["outline_variant"]), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.restore()


def soft_shadow(widget, blur: float = 8, dy: float = 2, alpha: int = 22) -> QGraphicsDropShadowEffect:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)
    return eff


def elevation_shadow(widget, blur: float = 24, dy: float = 6, alpha: int = 36) -> QGraphicsDropShadowEffect:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)
    return eff



class M3Style(QProxyStyle):
    """只接管勾选框 / 单选框的绘制：20dp 圆角方框 + 白色对勾；10dp 圆点。"""

    def __init__(self):
        super().__init__("Fusion")

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (QStyle.PixelMetric.PM_IndicatorWidth,
                      QStyle.PixelMetric.PM_IndicatorHeight):
            return 20
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        E = QStyle.PrimitiveElement
        if element in (E.PE_IndicatorCheckBox, E.PE_IndicatorItemViewItemCheck,
                       E.PE_IndicatorRadioButton):
            self._draw_indicator(element, option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_indicator(self, element, option, painter):
        E = QStyle.PrimitiveElement
        p = painter
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        st = option.state
        on = bool(st & QStyle.StateFlag.State_On)
        partial = bool(st & QStyle.StateFlag.State_NoChange)
        enabled = bool(st & QStyle.StateFlag.State_Enabled)
        hover = bool(st & QStyle.StateFlag.State_MouseOver)
        r = option.rect
        box = QRectF(r.center().x() - 10, r.center().y() - 10, 20, 20)
        line = QColor(COLORS["outline"])
        if not enabled:
            line = QColor(COLORS["outline_variant"])
        elif hover:
            line = QColor(COLORS["primary"])

        if element == E.PE_IndicatorRadioButton:
            if on:
                p.setPen(QPen(QColor(COLORS["primary"]), 2.0))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(box.adjusted(1, 1, -1, -1))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(COLORS["primary"]))
                p.drawEllipse(box.center(), 4.8, 4.8)
            else:
                p.setPen(QPen(line, 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(box.adjusted(0.7, 0.7, -0.7, -0.7))
            p.restore()
            return

        if on or partial:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLORS["primary"] if enabled else COLORS["outline_variant"]))
            p.drawRoundedRect(box, 5, 5)
            if enabled:
                p.setPen(QPen(QColor("#FFFFFF"), 2.2, Qt.SolidLine,
                              Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                if partial:
                    p.drawLine(QPointF(box.left() + 6, box.center().y()),
                               QPointF(box.right() - 6, box.center().y()))
                else:
                    path = QPainterPath(QPointF(box.left() + 5.0, box.center().y() + 0.6))
                    path.lineTo(box.left() + 8.6, box.bottom() - 5.4)
                    path.lineTo(box.right() - 4.6, box.top() + 5.6)
                    p.drawPath(path)
        else:
            p.setPen(QPen(line, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box.adjusted(0.7, 0.7, -0.7, -0.7), 5, 5)
        p.restore()


def apply_theme(app: QApplication) -> None:
    global FONT_SANS, FONT_SERIF, FONT_DISPLAY
    sans, _ = pick_font_family()
    FONT_SANS = f'"{sans}"'
    FONT_SERIF = FONT_SANS
    FONT_DISPLAY = FONT_SANS
    try:
        if not isinstance(app.style(), M3Style):
            app.setStyle(M3Style())
    except Exception:
        pass
    app.setStyleSheet(build_qss())
    f = QFont(sans, 10)
    f.setStyleStrategy(QFont.PreferAntialias)
    # 宋体在小字号下必须开完整 hinting：只开抗锯齿时 12~13px 的横画会糊成
    # 一片灰，看着不像宋体（像被虚化的黑体）。PreferFullHinting 让横竖笔画
    # 咬在像素格上，中文才是那种清爽的「印刷宋」。
    try:
        f.setHintingPreference(QFont.PreferFullHinting)
    except Exception:
        pass
    app.setFont(f)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(COLORS["surface"]))
    pal.setColor(QPalette.Base, QColor(COLORS["surface"]))
    pal.setColor(QPalette.Text, QColor(COLORS["on_surface"]))
    pal.setColor(QPalette.ButtonText, QColor(COLORS["on_surface"]))
    pal.setColor(QPalette.Highlight, QColor(COLORS["secondary_container"]))
    pal.setColor(QPalette.HighlightedText, QColor(COLORS["on_secondary_container"]))
    app.setPalette(pal)


def serif_style(size: int, color: str, weight: int = 400, extra: str = "") -> str:
    return (f'font-family:{FONT_SANS}; font-size:{size}px; font-weight:{weight};'
            f' color:{color};' + (" " + extra if extra else ""))


def type_style(key: str, color: str, px: int | None = None) -> str:
    size, line, weight, spacing = TYPE_SCALE.get(key, TYPE_SCALE["body_medium"])
    size = px or size
    return (f'font-family:{FONT_SANS}; font-size:{size}px; font-weight:{weight};'
            f' color:{color}; letter-spacing:{spacing}px;')


def display_font(size_px: int, weight: int = 400) -> QFont:
    f = QFont(FONT_SANS.strip('"'), 10)
    f.setPixelSize(size_px)
    f.setWeight(QFont.Weight(weight))
    f.setStyleStrategy(QFont.PreferAntialias)
    try:
        f.setFeature("tnum", 1)
    except Exception:
        pass
    return f
