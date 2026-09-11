# -*- coding: utf-8 -*-
"""
主题层：莫兰迪蓝主色 + 杂志感排版 + 手工感细节 + 丝滑动效曲线。
=========================================================================
设计要点（去“AI 味”方向）：
- 主色：雾霾蓝灰蓝系（#8BA8C7 一支），辅助：暖灰 / 米白 / 浅驼色；
  绝无荧光色、高饱和蓝、紫→蓝渐变、玻璃态。
- 排版：标题衬线体（Playfair Display，打包附带；回退 Georgia/KaiTi/宋体），
  正文无衬线（DM Sans / 微软雅黑），字号层级拉开，杂志感。
- 手工感：轻微偏移的双线边框、手绘波浪线、倾斜的有机色块、噪点纸纹。
- 动效：统一 cubic-bezier 缓动（预采样 LUT），0.3~0.6s，柔和不夸张。
=========================================================================
"""

from __future__ import annotations

import random

from PySide6.QtCore import Qt, QRectF, QPointF, QEasingCurve
from PySide6.QtGui import QColor, QLinearGradient, QPixmap, QPainter, QBrush, QFont, QPalette
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

# ---------------------------------------------------------------------------
# 莫兰迪色板（蓝为主，暖灰/米白/浅驼辅助；严格无高饱和）
# ---------------------------------------------------------------------------

COLORS = {
    "blue": "#8BA8C7",          # 雾霾蓝（主）
    "blue_dark": "#7593B4",     # 雾霾蓝深（按压/强调字）
    "blue_deep": "#5F7C9C",     # 更深的雾霾蓝（仅文字/稀有强调）
    "blue_soft": "#DCE6F0",     # 雾霾蓝浅（状态层/高亮）
    "pink": "#D4A5A5",          # 豆沙粉（警示辅助）
    "pink_dark": "#B4717C",
    "green": "#A8B5A0",         # 灰豆绿（成功辅助）
    "green_dark": "#93A18B",
    "green_soft": "#DFE5DA",
    "warmgray": "#D4CFC9",      # 暖灰（边框）
    "cream": "#F5F0EB",         # 米白（窗口底）
    "paper": "#FBF8F4",         # 纸面（表面）
    "paper_deep": "#F6F1EB",    # 纸面深（分区底）
    "camel": "#C9B08C",         # 浅驼色（装饰性辅助：线条/小色块/斜体点缀）
    "camel_soft": "#E5DBC7",    # 浅驼色浅
    "camel_deep": "#8A6F4E",
    "ink": "#4B4741",           # 墨色（正文）
    "ink_soft": "#8C857B",      # 墨色浅（次要文字）
    "ink_faint": "#B5AEA4",     # 墨色更浅（占位/禁用）
    "line": "#E3DCD2",          # 细分隔线
    "line_soft": "#EDE7DE",     # 更浅分隔线
    "scrim": (26, 22, 16),      # 弹窗遮罩底色（暖黑）
    "shadow": (26, 22, 14),     # 阴影基色（低透明度暖黑）
}

# 状态层颜色（M3：on-surface / on-primary 的 8%~12% 叠加，用莫兰迪近似色）
STATE_HOVER = "#F1ECE5"      # on-surface @8%
STATE_PRESS = "#E9E3DA"      # on-surface @12%
STATE_PRIMARY_HOVER = "#93AECB"   # primary + on-primary @8%
STATE_PRIMARY_PRESS = "#6C89A9"   # primary + on-primary @12%
STATE_TONAL_HOVER = "#D4DEE9"     # primary-container + on-primary-container @8%
STATE_TONAL_PRESS = "#CBD7E4"     # @12%

# ---------------------------------------------------------------------------
# 字体（运行时可自适应；打包附带了 Playfair Display / DM Sans）
# ---------------------------------------------------------------------------

FONT_SANS = '"Microsoft YaHei UI"'          # 正文无衬线（运行时时更新）
FONT_SERIF = '"Playfair Display"'            # 标题/数字衬线（运行时时更新）

_SERIF_CANDIDATES = ("Playfair Display", "Georgia", "Times New Roman",
                     "KaiTi", "楷体", "STKaiti", "SimSun")
_SANS_CANDIDATES = ("DM Sans", "Inter", "Microsoft YaHei UI", "Microsoft YaHei",
                    "Noto Sans SC", "SimHei", "Segoe UI")


def register_fonts(base_dir) -> None:
    """
    从 assets/fonts 注册打包附带的字体（Playfair Display / DM Sans，OFL 协议）。
    base_dir：源代码运行 = 项目根；打包运行 = sys._MEIPASS。
    成功与否不影响程序（会自动回退到系统字体）。
    """
    import sys
    from PySide6.QtGui import QFontDatabase
    fdir = None
    for cand in (getattr(sys, "_MEIPASS", None), base_dir):
        if cand:
            p = f"{cand}/assets/fonts"
            import os
            if os.path.isdir(p):
                fdir = p
                break
    if not fdir:
        return
    import os
    for fn in sorted(os.listdir(fdir)):
        if fn.lower().endswith((".ttf", ".otf")):
            try:
                QFontDatabase.addApplicationFont(os.path.join(fdir, fn))
            except Exception:
                pass


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
    """返回 (正文字体, 标题衬线字体)，按系统实际安装自适应。"""
    sans = _first_available(_SANS_CANDIDATES)
    serif = _first_available(_SERIF_CANDIDATES)
    return sans, serif


# ---------------------------------------------------------------------------
# 自定义缓动曲线：cubic-bezier 预采样（Qt 无原生 bezier，这里用 LUT 实现）
# ---------------------------------------------------------------------------

_curve_cache: dict = {}


def bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    """
    生成立方贝塞尔缓动 QEasingCurve（0.3~0.6s 动效统一用）。
    用法：anim.setEasingCurve(bezier(0.22, 0.61, 0.36, 1.0))
    """
    key = (round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))
    if key in _curve_cache:
        return _curve_cache[key]

    # 参数化采样：t in [0,1]，按 x 单调建立 LUT
    table = [0.0] * 256

    def cubic(a, b, u):
        return 3 * (1 - u) * u * u * a + 3 * (1 - u) * u * u * b + u ** 3

    pts = []
    steps = 512
    prev_x = -1.0
    for i in range(steps + 1):
        u = i / steps
        x = cubic(x1, x2, u)
        y = cubic(y1, y2, u)
        if x < 0 or x > 1:
            continue
        if x < prev_x:
            continue
        prev_x = x
        pts.append((x, y))
    for k in range(256):
        target = k / 255.0
        # 找到 pts 中第一个 x >= target 的点做线性插值
        y = target
        for j in range(1, len(pts)):
            if pts[j][0] >= target:
                (xa, ya), (xb, yb) = pts[j - 1], pts[j]
                span = (xb - xa) or 1e-9
                y = ya + (yb - ya) * (target - xa) / span
                break
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


# 常用曲线：ease-out 系列（柔和、无夸张过冲）
def ease_out() -> QEasingCurve:      return bezier(0.22, 0.61, 0.36, 1.0)
def ease_out_quint() -> QEasingCurve: return bezier(0.22, 1.0, 0.36, 1.0)
def ease_in_out() -> QEasingCurve:   return bezier(0.65, 0.0, 0.35, 1.0)
def ease_out_back() -> QEasingCurve:  return bezier(0.34, 1.3, 0.64, 1.0)   # 温和回弹
def ease_in() -> QEasingCurve:       return bezier(0.55, 0.055, 0.675, 0.19)


# ---------------------------------------------------------------------------
# 全局 QSS（排版层级：标题衬线 / 正文无衬线；状态层；无明显圆角堆砌）
# ---------------------------------------------------------------------------

def build_qss() -> str:
    c = COLORS
    return f"""
* {{
    font-family: {FONT_SANS};
    outline: none;
}}

QMainWindow, QDialog {{
    background-color: {c['cream']};
}}

/* ============ 顶栏（透明底色 + 发丝线；有机背景可见） ============ */
#TopBar {{
    background: transparent;
    border-bottom: 1px solid {c['line']};
}}

#AppTitle {{
    font-family: {FONT_SERIF};
    color: {c['ink']};
    font-size: 24px;
    font-weight: 600;
    letter-spacing: 1px;
}}

#AppCaption {{
    font-family: {FONT_SERIF};
    color: {c['camel']};
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 3px;
}}

#ModeBadge {{
    background-color: {c['blue_soft']};
    color: {c['blue_deep']};
    border: none;
    border-radius: 11px;
    padding: 6px 14px;
    font-size: 12.5px;
    font-weight: 600;
}}

/* ============ 表面卡片（自绘为主，QSS 兜底） ============ */
QFrame[card="true"] {{
    background-color: {c['paper']};
    border: none;
    border-radius: 14px;
}}

QLabel[cardTitle="true"] {{
    font-family: {FONT_SERIF};
    color: {c['ink']};
    font-size: 17px;
    font-weight: 600;
}}

QLabel[cardHint="true"] {{
    color: {c['ink_soft']};
    font-size: 12.5px;
}}

/* ============ 按钮（圆角矩形；Material 状态层） ============ */
/* Outlined：透明底 + outline 边框 */
QPushButton {{
    background-color: transparent;
    color: {c['ink']};
    border: 1px solid {c['warmgray']};
    border-radius: 12px;
    padding: 0 24px;
    font-size: 15px;
    font-weight: 500;
    min-height: 48px;
}}
QPushButton:hover {{ background-color: {STATE_HOVER}; border-color: {c['ink_faint']}; }}
QPushButton:pressed {{
    background-color: {STATE_PRESS};
    padding-top: 3px;
}}
QPushButton:disabled {{
    color: {c['ink_faint']};
    background-color: {c['paper_deep']};
    border-color: {c['line_soft']};
}}

/* Filled：主按钮（primary / on-primary） */
QPushButton[type="primary"] {{
    color: #FFFFFF;
    background-color: {c['blue']};
    border: none;
    border-radius: 12px;
    font-size: 15.5px;
    font-weight: 600;
    padding: 0 24px;
}}
QPushButton[type="primary"]:hover {{ background-color: {STATE_PRIMARY_HOVER}; }}
QPushButton[type="primary"]:pressed {{ background-color: {STATE_PRIMARY_PRESS}; padding-top: 3px; }}
QPushButton[type="primary"]:disabled {{
    color: rgba(255,255,255,0.72);
    background-color: {c['blue_soft']};
}}

/* Tonal：次强调（error-container / on-error-container） */
QPushButton[type="danger"] {{
    color: {c['pink_dark']};
    background-color: #F0DFDC;
    border: none;
    border-radius: 12px;
    font-weight: 600;
}}
QPushButton[type="danger"]:hover {{ background-color: #EBD5D0; }}
QPushButton[type="danger"]:pressed {{ background-color: #E5CAC3; padding-top: 3px; }}

/* Tonal：成功（secondary-container / on-secondary-container） */
QPushButton[type="green"] {{
    color: {c['green_dark']};
    background-color: {c['green_soft']};
    border: none;
    border-radius: 12px;
    font-weight: 600;
}}
QPushButton[type="green"]:hover {{ background-color: #D5DCCD; }}

/* Text：文字按钮 */
QPushButton[type="ghost"] {{
    background: transparent;
    border: none;
    border-radius: 10px;
    color: {c['ink_soft']};
    font-size: 14.5px;
    font-weight: 500;
    min-height: 44px;
    padding: 0 16px;
}}
QPushButton[type="ghost"]:hover {{ color: {c['blue_deep']}; background-color: {STATE_HOVER}; }}
QPushButton[type="ghost"]:pressed {{ background-color: {STATE_PRESS}; padding-top: 2px; }}

/* 弹窗操作按钮（Text / Filled，圆角矩形） */
QPushButton[mtype="action"] {{
    background: transparent;
    border: none;
    border-radius: 12px;
    color: {c['blue_deep']};
    font-size: 14.5px;
    font-weight: 700;
    min-height: 46px;
    padding: 0 20px;
}}
QPushButton[mtype="action"]:hover {{ background-color: {STATE_TONAL_HOVER}; }}
QPushButton[mtype="action"]:pressed {{ background-color: {STATE_TONAL_PRESS}; }}

QPushButton[mtype="action-primary"] {{
    background-color: {c['blue']};
    border: none;
    border-radius: 12px;
    color: #FFFFFF;
    font-size: 14.5px;
    font-weight: 700;
    min-height: 46px;
    padding: 0 22px;
}}
QPushButton[mtype="action-primary"]:hover {{ background-color: {STATE_PRIMARY_HOVER}; }}
QPushButton[mtype="action-primary"]:pressed {{ background-color: {STATE_PRIMARY_PRESS}; }}
QPushButton[mtype="action-primary"]:disabled {{
    background-color: {c['blue_soft']};
    color: rgba(255,255,255,0.72);
}}

/* 主操作大按钮（圆角矩形大按钮；primary-container / on-primary-container） */
QPushButton[type="fab"] {{
    color: {c['blue_deep']};
    background-color: {c['blue_soft']};
    border: none;
    border-radius: 16px;
    font-size: 18px;
    font-weight: 700;
    padding: 0 32px;
}}
QPushButton[type="fab"]:hover {{ background-color: {STATE_TONAL_HOVER}; }}
QPushButton[type="fab"]:pressed {{ background-color: {STATE_TONAL_PRESS}; }}
QPushButton[type="fab"]:disabled {{
    color: rgba(95,124,156,0.5);
    background-color: {c['paper_deep']};
}}

/* ============ 输入控件（M3：全圆角 pill） ============ */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {c['paper']};
    color: {c['ink']};
    border: 1px solid {c['warmgray']};
    border-radius: 99px;
    padding: 0 18px;
    min-height: 46px;
    font-size: 15px;
    selection-background-color: {c['blue_soft']};
    selection-color: {c['ink']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c['blue']};
    background-color: #FFFFFF;
}}
QLineEdit:disabled {{
    color: {c['ink_faint']};
    background-color: {c['paper_deep']};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {c['paper_deep']};
    border: none;
    width: 34px;
    border-left: 1px solid {c['line_soft']};
}}
QSpinBox::up-button {{
    border-top-right-radius: 99px;
}}
QSpinBox::down-button {{
    border-bottom-right-radius: 99px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {c['blue_soft']};
}}

QComboBox::drop-down {{
    border: none;
    width: 38px;
    background: {c['paper_deep']};
    border-left: 1px solid {c['line_soft']};
    border-top-right-radius: 99px;
    border-bottom-right-radius: 99px;
}}
QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    color: {c['ink']};
    border: 1px solid {c['warmgray']};
    border-radius: 16px;
    padding: 6px;
    selection-background-color: {c['blue_soft']};
    selection-color: {c['ink']};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 42px;
    padding: 0 12px;
    border-radius: 99px;
}}

/* ============ 表格 / 列表（表面；16px 圆角） ============ */
QTableWidget, QListWidget {{
    background-color: #FFFFFF;
    alternate-background-color: #FCFAF7;
    border: 1px solid {c['line']};
    border-radius: 16px;
    color: {c['ink']};
    font-size: 14px;
    gridline-color: {c['line_soft']};
}}
QTableWidget::item {{ padding: 5px 10px; }}
QTableWidget::item:selected, QListWidget::item:selected {{
    background-color: {c['blue_soft']};
    color: {c['ink']};
}}
QListWidget::item {{
    padding: 4px 10px;
    border-radius: 12px;
}}
QListWidget::item:hover {{ background-color: {STATE_HOVER}; }}
QHeaderView::section {{
    background-color: {c['paper_deep']};
    color: {c['ink_soft']};
    border: none;
    border-right: 1px solid {c['line_soft']};
    border-bottom: 1px solid {c['line']};
    padding: 9px 12px;
    font-size: 13px;
    font-weight: 700;
}}
QTableCornerButton::section {{
    background-color: {c['paper_deep']};
    border: none;
}}

/* ============ 滚动条 ============ */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c['warmgray']};
    border-radius: 6px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['ink_faint']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c['warmgray']};
    border-radius: 6px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ============ 复选 / 单选 ============ */
QCheckBox, QRadioButton {{
    color: {c['ink']};
    font-size: 14px;
    spacing: 8px;
    min-height: 32px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 22px;
    height: 22px;
    border: 1px solid {c['warmgray']};
    border-radius: 6px;
    background: #FFFFFF;
}}
QRadioButton::indicator {{ border-radius: 11px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c['blue']};
    border-color: {c['blue_dark']};
}}

/* ============ 菜单 / 提示 ============ */
QToolTip {{
    background-color: {c['ink']};
    color: {c['cream']};
    border: none;
    padding: 6px 10px;
    font-size: 12px;
    border-radius: 8px;
}}
QMenu {{
    background-color: #FFFFFF;
    border: 1px solid {c['warmgray']};
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{
    padding: 10px 26px;
    min-height: 40px;
    font-size: 14px;
    color: {c['ink']};
    border-radius: 8px;
}}
QMenu::item:selected {{ background-color: {c['blue_soft']}; }}
"""


# ---------------------------------------------------------------------------
# 纸纹噪点（低存在感）
# ---------------------------------------------------------------------------

_texture_cache: QPixmap | None = None


def paper_texture() -> QPixmap:
    """生成 96x96 暖色噪点纹理（固定种子，稳定不变）。"""
    global _texture_cache
    if _texture_cache is not None:
        return _texture_cache
    size = 96
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    rnd = random.Random(20260904)
    for _ in range(360):
        x, y = rnd.randint(0, size - 1), rnd.randint(0, size - 1)
        a = rnd.randint(3, 9)
        shade = rnd.choice([(0, 0, 0), (255, 255, 255), (140, 110, 60)])
        p.setPen(QColor(shade[0], shade[1], shade[2], a))
        p.drawPoint(x, y)
    p.end()
    _texture_cache = pm
    return pm


def paint_paper(painter: QPainter, rect: QRectF, base: str | None = None,
                radius: float = 14.0) -> None:
    """表面卡片绘制：垂直微渐变 + 极淡噪点 + 1px 浅描边。"""
    c = COLORS
    base_q = QColor(base or c["paper"])
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    grad.setColorAt(0.0, base_q.lighter(101))
    grad.setColorAt(1.0, base_q.darker(102))
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRoundedRect(rect, radius, radius)
    painter.setClipRect(rect)
    painter.setOpacity(0.35)
    painter.drawTiledPixmap(rect.toRect(), paper_texture())
    painter.restore()
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    pen = painter.pen()
    pen.setColor(QColor(c["line_soft"]))
    pen.setWidthF(1.0)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.restore()


def soft_shadow(widget, blur: float = 26, dy: float = 5, alpha: int = 38) -> QGraphicsDropShadowEffect:
    """柔和阴影（卡片高程）。"""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(*COLORS["shadow"], alpha))
    widget.setGraphicsEffect(eff)
    return eff


def elevation_shadow(widget, blur: float = 36, dy: float = 8, alpha: int = 58) -> QGraphicsDropShadowEffect:
    """大而轻的高程阴影（弹窗/浮层）。"""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(*COLORS["shadow"], alpha))
    widget.setGraphicsEffect(eff)
    return eff


# ---------------------------------------------------------------------------
# 应用主题
# ---------------------------------------------------------------------------

def apply_theme(app: QApplication) -> None:
    """按系统字体自适应设置全局主题。"""
    global FONT_SANS, FONT_SERIF
    sans, serif = pick_font_family()
    FONT_SANS = f'"{sans}"'
    FONT_SERIF = f'"{serif}"'
    app.setStyleSheet(build_qss())
    f = QFont(sans, 10)
    f.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(f)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(COLORS["cream"]))
    pal.setColor(QPalette.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.Text, QColor(COLORS["ink"]))
    pal.setColor(QPalette.ButtonText, QColor(COLORS["ink"]))
    pal.setColor(QPalette.Highlight, QColor(COLORS["blue_soft"]))
    pal.setColor(QPalette.HighlightedText, QColor(COLORS["ink"]))
    app.setPalette(pal)


def serif_style(size: int, color: str, weight: int = 600, extra: str = "") -> str:
    """标题的衬线样式字符串（页面标题用）。"""
    return (f'font-family:{FONT_SERIF}; font-size:{size}px; font-weight:{weight};'
            f' color:{color};' + (" " + extra if extra else ""))
