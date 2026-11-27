# -*- coding: utf-8 -*-
"""
极致动效引擎
=========================================================================
核心：MotionEffect（自定义 QGraphicsEffect）把 widget 连同它的所有子控件
一起做「缩放 / 位移 / 旋转 / 透明度」合成，动画只改效果参数，绝不改
widget 的 pos / geometry —— 因此永远不会和布局打架、不会累积漂移。

性能：QGraphicsEffect 默认每帧都把整棵子树重渲进 sourcePixmap（实测
2.5~9ms/帧），而动画期间子树内容并不变。MotionEffect 因此缓存源位图，
只在「子树内任意控件重绘 / 自身内容被外部改写 / 尺寸变化」时失效——
每帧成本降到一次 drawPixmap（~0.1ms），动画全程不掉帧。

弹簧曲线用手写欠阻尼解（比 OutBack 更有生命力，可过冲回弹）。
"""
from __future__ import annotations

import math

from PySide6.QtCore import (Qt, QPoint, QPointF, QEasingCurve, QVariantAnimation,
                            QTimer, QObject, QEvent)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QGraphicsEffect, QWidget, QApplication


# ---------------------------------------------------------------------------
# 曲线
# ---------------------------------------------------------------------------
def spring(t: float, omega: float = 11.0, zeta: float = 0.52) -> float:
    """欠阻尼弹簧：0 → 过冲 ~1.1 → 回落 1。t∈[0,1]。"""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    wd = omega * math.sqrt(max(1e-6, 1.0 - zeta * zeta))
    return 1.0 - math.exp(-zeta * omega * t) * (
        math.cos(wd * t) + (zeta * omega / wd) * math.sin(wd * t))


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_out_quint(t: float) -> float:
    return 1.0 - (1.0 - t) ** 5


def ease_in(t: float) -> float:
    return t * t * t


# ---------------------------------------------------------------------------
# 源位图缓存失效网络
# ---------------------------------------------------------------------------
# 策略：app 级 Paint 监听。
#   - 实测（probe_paint_order）：纯特效动画帧只触发 MotionEffect.draw()，
#     Qt 不会给控件发 Paint 事件、也不会重渲源位图——所以动画期间缓存天然
#     有效，每帧只剩一次 drawPixmap 合成；
#   - 一旦子树内任意控件「真正变脏」（子动画 / 涟漪 / 列表刷新 / 外部
#     setText / 尺寸变化），Qt 会重渲源位图并给相关控件发 Paint 事件——
#     此时沿父链向上失效所有祖先特效的缓存，下一帧按新内容重取源。
# 注意：不能按 UpdateRequest 过滤——它只投递给顶层窗口，区分不了来源。
class _SubtreePaintTap(QObject):
    def __init__(self):
        super().__init__()
        self._installed = False

    def ensure(self):
        if self._installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._installed = True

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Paint:
            return False
        w = obj if isinstance(obj, QWidget) else None
        if w is None:
            return False
        eff = w.graphicsEffect()
        if isinstance(eff, MotionEffect):
            eff.invalidate()
        p = w.parentWidget()
        while p is not None:
            pe = p.graphicsEffect()
            if isinstance(pe, MotionEffect):
                pe.invalidate()
            p = p.parentWidget()
        return False


_TAP = _SubtreePaintTap()


def invalidate(widget: QWidget):
    """外部改写 widget 内容后调用：作废其 MotionEffect 的源位图缓存。"""
    try:
        eff = widget.graphicsEffect()
        if isinstance(eff, MotionEffect):
            eff.invalidate()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 效果
# ---------------------------------------------------------------------------
class MotionEffect(QGraphicsEffect):
    """对源 pixmap 做变换后绘制；四个参数均由动画驱动。

    **只做几何变换，不合成任何阴影。** 早期版本会在动画期间用源位图模糊出
    一张「影子」画在卡片下方（因为 QGraphicsEffect 不能叠加，接管卡片时
    原生投影会被顶掉）。那条路彻底废弃：源位图里已经带着卡片自己的圆角、
    描边和内容，模糊出来的是一块位置对不上、还会随缩放忽隐忽现的灰块，
    在 125% 缩放下 `copy()` 的偏移量还是设备像素/逻辑像素混用——影子直接
    偏出十几像素。卡片阴影现在由卡片自己在 paintEvent 里画，与动画无关。

    出框：重写 boundingRectFor 把裁剪区扩出去，做真正的「向外弹出」。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.s = 1.0
        self.dx = 0.0
        self.dy = 0.0
        self.a = 1.0
        self.rot = 0.0
        self._hue = None           # 可选：整体叠一层色调（高亮反馈）
        # —— 源位图缓存 ——
        self._src = None           # 缓存的源位图（子树静态时跨帧复用）
        self._src_key = None       # 缓存键：(宽, 高, DPR)
        self._src_off = QPoint(0, 0)   # 位图相对控件左上角的偏移（出框时 < 0）
        # —— 出框余量（动画启动时按参数一次算好，避免逐帧变化的重绘区） ——
        self._bleed = 0.0

    # ---- 缓存管理 ----
    def invalidate(self):
        self._src = None
        self._src_key = None
        self._src_off = QPoint(0, 0)

    def _widget(self):
        p = self.parent()
        return p if isinstance(p, QWidget) else None

    def _source(self):
        """取源位图 + 绘制偏移：缓存命中直接复用（每帧省一次整棵子树重渲）。

        两处必须一起处理，否则画面会「跳」：

        1. **偏移**：boundingRectFor 被扩大后（出框余量 / 投影外扩），
           sourcePixmap 返回的位图比控件本身大一圈，并给出一个负的 offset
           （实测 400x300 的控件 → 480x380 的位图，offset=(-40,-40)）。
           按 (0,0) 画就会让内容整体偏移 bleed 像素，动画结束效果一禁用又
           瞬间弹回——用户看到的就是「跳一下」，而且横向最明显。
        2. **缓存键**：必须用请求时的控件逻辑尺寸 + DPR，不能用返回位图的
           像素尺寸反推（高 DPI 或控件被裁剪时两者永不相等，缓存会逐帧失效，
           实测 700ms 重渲 44 次）。
        """
        w = self._widget()
        try:
            dpr = round(w.devicePixelRatioF(), 3) if w is not None else 1.0
        except Exception:
            dpr = 1.0
        key = (w.width(), w.height(), dpr) if w is not None else None
        if (self._src is not None and not self._src.isNull()
                and self._src_key == key):
            return self._src
        off = QPoint(0, 0)
        pm = None
        try:
            pm = self.sourcePixmap(Qt.LogicalCoordinates, off)
        except TypeError:
            # 老版本 PySide6 没有 offset 输出参数，退回单参数调用
            try:
                pm = self.sourcePixmap(Qt.LogicalCoordinates)
            except Exception:
                pm = None
            off = QPoint(0, 0)
        except Exception:
            pm = None
        if pm is None or pm.isNull():
            return None
        self._src = pm
        self._src_key = key
        self._src_off = off
        return pm

    def boundingRectFor(self, rect):
        m = self._bleed
        if m <= 1.0:
            return rect
        return rect.adjusted(-m, -m, m, m)

    def set_values(self, s=None, dx=None, dy=None, a=None, rot=None):
        import shiboken6
        if not shiboken6.isValid(self):
            return
        if s is not None:
            self.s = float(s)
        if dx is not None:
            self.dx = float(dx)
        if dy is not None:
            self.dy = float(dy)
        if a is not None:
            self.a = float(a)
        if rot is not None:
            self.rot = float(rot)
        # 注意：这里只触发 effect 重绘（draw），不会给控件发 Paint 事件、
        # 也不会让 Qt 重渲源位图——缓存因此可以跨帧复用（见文件头说明）。
        self.update()

    def draw(self, painter):
        pm = self._source()
        if pm is None or pm.isNull():
            self.drawSource(painter)
            return
        off = self._src_off
        ox, oy = int(round(off.x())), int(round(off.y()))
        changed = (abs(self.s - 1.0) > 1e-3 or abs(self.dx) > 0.1
                   or abs(self.dy) > 0.1 or abs(self.a - 1.0) > 1e-3
                   or abs(self.rot) > 0.01)
        if not changed and self._hue is None:
            self.drawSource(painter)
            return
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, self.a)))
        # 变换支点用「控件中心在位图坐标系里的位置」：位图可能带出框留白
        # （offset 为负），直接用 pm 的几何中心会在留白不对称时偏。
        wdg = self._widget()
        if wdg is not None:
            c = QPointF(wdg.width() / 2.0 - ox, wdg.height() / 2.0 - oy)
        else:
            c = QPointF(pm.width() / 2.0, pm.height() / 2.0)
        if changed:
            if self._bleed > 0:
                # 已重写 boundingRectFor 扩大裁剪区：允许出框，原样变换。
                s = self.s
            else:
                # 兜底路径（未申请出框余量）：把变换夹在 rect 内，避免切平。
                s = min(self.s, 1.0)
                need = max(abs(self.dx), abs(self.dy))
                if need > 0.5:
                    fx = (pm.width() - 2.0 * need) / max(1.0, pm.width())
                    fy = (pm.height() - 2.0 * need) / max(1.0, pm.height())
                    s = min(s, max(0.70, min(fx, fy)))
                if abs(self.rot) > 0.3:
                    s = min(s, 0.90)   # 旋转时角部会越界，额外留余量
            dx = self.dx
            dy = self.dy
            if self._bleed <= 0:
                free = (1.0 - s) * pm.width() / 2.0
                free_y = (1.0 - s) * pm.height() / 2.0
                dx = max(-free, min(free, dx))
                dy = max(-free_y, min(free_y, dy))
            if abs(s - 1.0) < 1e-4 and abs(self.rot) < 0.01:
                # 纯平移：偏移取整像素。painter.translate(浮点) 会让整张位图
                # 走双线性重采样——150px 的大数字在位移过程中会明显发虚，
                # 这正是「入场时数字糊一下」的来源。取整后是像素级硬搬运。
                painter.translate(round(dx), round(dy))
            else:
                painter.translate(c.x() + dx, c.y() + dy)
                if abs(self.rot) > 0.01:
                    painter.rotate(self.rot)
                painter.scale(s, s)
                painter.translate(-c.x(), -c.y())
        painter.drawPixmap(ox, oy, pm)
        if self._hue is not None:
            painter.setOpacity(self._hue.alphaF())
            if wdg is not None:
                painter.fillRect(ox, oy, wdg.width(), wdg.height(), self._hue)
            else:
                painter.fillRect(pm.rect(), self._hue)
        painter.restore()



# ---------------------------------------------------------------------------
# 驱动
# ---------------------------------------------------------------------------
def _effect(widget: QWidget):
    """取（或建）该 widget 的 MotionEffect。

    只接管「占位但不影响观感」的 effect：任何 QGraphicsDropShadowEffect 都
    已经在源码里清掉了，这里遇到其他 effect 直接顶替——动画结束后不回装，
    避免出现「动画中是 A、静止后是 B」的视觉切换。
    """
    _TAP.ensure()
    eff = widget.graphicsEffect()
    if isinstance(eff, MotionEffect):
        return eff
    eff = MotionEffect(widget)
    widget.setGraphicsEffect(eff)
    return eff


def _stop(widget: QWidget):
    old = getattr(widget, "_motion_anim", None)
    if old is not None:
        try:
            old.stop()
        except Exception:
            pass
        widget._motion_anim = None


def animate(widget: QWidget, *, dur: int = 520, delay: int = 0,
            s0=1.0, s1=1.0, dx0=0.0, dx1=0.0, dy0=0.0, dy1=0.0,
            a0=1.0, a1=1.0, rot0=0.0, rot1=0.0,
            curve=None, keep_effect: bool = False, on_done=None):
    """通用变换动画；curve 默认弹簧（退场可传 ease_in）。

    s>1 现在是**真正的向外弹出**：MotionEffect 会按本次动画的极值申请
    出框余量（boundingRectFor 扩裁剪区），不再被迫换算成内缩。
    """

    def _run():
        import shiboken6
        if not shiboken6.isValid(widget):
            return
        if not widget.isVisible():
            if on_done:
                on_done()
            return
        _stop(widget)
        eff = _effect(widget)
        # 动画启动：内容可能已变化（如刚 setText / 刚刷新列表），先作废旧缓存
        eff.invalidate()
        # 出框余量：取本次动画的位移与放大极值，一次算好（逐帧变化会让
        # Qt 每帧重算脏区，反而更贵）。
        half_diag = math.hypot(widget.width(), widget.height()) / 2.0
        max_shift = max(abs(dx0), abs(dx1), abs(dy0), abs(dy1))
        max_scale = max(s0, s1, 1.0)
        # 取整：留白必须是整数，否则 sourcePixmap 的 offset 带小数，内容每帧
        # 都落在半个像素上，又会走重采样把文字糊掉。
        eff._bleed = float(math.ceil(
            max(max_shift, (max_scale - 1.0) * half_diag) + 3.0))
        # 重新启用效果管线（上一段动画结束后可能被禁用，见 _done）
        try:
            eff.setEnabled(True)
        except Exception:
            pass
        cv = curve or spring
        anim = QVariantAnimation(widget)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(max(60, dur))

        def _frame(v):
            import shiboken6
            if not shiboken6.isValid(eff) or not shiboken6.isValid(widget):
                try:
                    anim.stop()
                except Exception:
                    pass
                return
            t = float(v)
            k = cv(t)
            lerp = lambda p, q: p + (q - p) * k
            eff.set_values(s=lerp(s0, s1), dx=lerp(dx0, dx1),
                           dy=lerp(dy0, dy1), a=lerp(a0, a1),
                           rot=lerp(rot0, rot1))

        anim.valueChanged.connect(_frame)

        def _done():
            import shiboken6
            if not shiboken6.isValid(widget) or not shiboken6.isValid(eff):
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass
                return
            # 只把参数复位到「无变换」，不销毁 effect：
            # setGraphicsEffect(None) 会删除 C++ 对象，若别的动画仍在 tick
            # 就会触发 "Internal C++ object already deleted"。
            eff.set_values(s=s1, dx=dx1, dy=dy1, a=a1, rot=rot1)
            # 回到无变换状态后把效果「禁用」而不是留着：带 effect 的控件
            # 每次重绘都会把整棵子树渲进效果源位图（实测 hero 约 3ms/次），
            # 抽号滚动时大数字每 38ms 重绘一次就被拖慢。禁用后该控件回到
            # 普通绘制路径，效果对象保留（无删除竞态），下次动画再启用。
            # 注意：只有终点确实是「无变换」才禁用；淡出结束(a<1)等状态
            # 必须保留效果，否则控件会重新变回完全不透明。
            identity = (abs(s1 - 1.0) < 1e-3 and abs(dx1) < 0.1
                        and abs(dy1) < 0.1 and abs(a1 - 1.0) < 1e-3
                        and abs(rot1) < 0.01)
            if identity:
                eff._bleed = 0.0
                try:
                    eff.setEnabled(False)
                except Exception:
                    pass
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass

        anim.finished.connect(_done)
        widget._motion_anim = anim
        # 关键：先同步落到首帧再 start()。
        # QVariantAnimation.start() 不会立即发 valueChanged，首个动画帧要等
        # 下一个事件循环 tick —— 这中间会以「没有动画」的原样绘制一帧，
        # 于是每次入场都是「先全亮一帧，再跳回透明重新淡入」，看起来像闪。
        _frame(0.0)
        anim.start()

    if delay > 0:
        # 延迟启动也必须**立刻**落到起点：否则控件会先以终态原样亮着，
        # 等 delay 到点才跳回 s0/dy0/a0 重新播——看起来就是「先闪一下、
        # 再从头淡入」。stagger() 里除第一个之外的元素都会走到这里。
        try:
            import shiboken6
            if shiboken6.isValid(widget) and widget.isVisible():
                eff = _effect(widget)
                half_diag = math.hypot(widget.width(), widget.height()) / 2.0
                eff._bleed = float(math.ceil(
                    max(max(abs(dx0), abs(dx1), abs(dy0), abs(dy1)),
                        (max(s0, s1, 1.0) - 1.0) * half_diag) + 3.0))
                eff.invalidate()
                try:
                    eff.setEnabled(True)
                except Exception:
                    pass
                eff.set_values(s=s0, dx=dx0, dy=dy0, a=a0, rot=rot0)
        except Exception:
            pass
        QTimer.singleShot(delay, _run)
    else:
        _run()


def pop_in(widget, *, dy=30, s=0.88, dur=560, delay=0, dx=0.0,
           rot=0.0, on_done=None):
    """弹性入场：从下方 + 缩小 + 透明，过冲回弹到原位。"""
    animate(widget, dur=dur, delay=delay, s0=s, s1=1.0,
            dx0=dx, dx1=0.0, dy0=dy, dy1=0.0,
            a0=0.0, a1=1.0, rot0=rot, rot1=0.0, on_done=on_done)


def pop_out(widget, *, dy=16, s=0.93, dur=280, on_done=None):
    """退场：干脆下沉缩小淡出（不用弹簧，收得利落）。"""
    animate(widget, dur=dur, s0=1.0, s1=s, dy0=0.0, dy1=dy,
            a0=1.0, a1=0.0, curve=ease_in, on_done=on_done)


def slide_switch(widget, on_mid, *, forward=True, dur=520):
    """内容切换：向侧滑出 → 换内容 → 从另一侧弹性滑入。"""
    d = 42 if forward else -42

    def _out_done():
        try:
            on_mid()
        except Exception:
            pass
        # 内容已整批换掉：作废缓存，下一帧按新内容重渲
        try:
            eff = widget.graphicsEffect()
            if isinstance(eff, MotionEffect):
                eff.invalidate()
        except Exception:
            pass
        animate(widget, dur=int(dur * 0.62),
                dx0=-d, dx1=0.0, s0=0.965, s1=1.0,
                a0=0.0, a1=1.0)

    animate(widget, dur=int(dur * 0.38), dx0=0.0, dx1=d,
            a0=1.0, a1=0.0, curve=ease_in,
            keep_effect=True, on_done=_out_done)


def page_enter(widget, *, dur=240, dy=8, delay=0, s0=1.0, a0=1.0, on_done=None):
    """整页入场：短促上浮，**不做缩放、也不做整体淡入**。

    参数是反复试出来的，每一条都对应一个看得见的问题：

    1. 不做缩放。哪怕 s=0.988，整页也要走一次双线性重采样，150px 的大数字
       在位移过程中会「糊一下」——大面积缩放是廉价感的主要来源。
    2. 位移只用 8px，且 draw() 对纯平移取整像素（见 MotionEffect.draw），
       位图是硬搬运，文字全程清晰。
    3. **不做整体淡入（a 恒为 1）**。主窗口是无边框半透明窗口，整棵树都在
       同一张 backing store 上合成，页面又是透明背景：只要 a<1，露出来的
       就不是底色，而是**上一个页面留在这块缓冲里的像素** —— 连点 Tab 时
       上一页的表头会一直隐隐透在新页顶上，看到的就是「残影」。
       实测 a=0.99 都能看见（文字是深色压浅底，1% 残留就够）。位移不会：
       页面始终不透明，每一帧都把整块盖住。
    4. delay 必须为 0。任何延迟都会让页面先以「终态」画一帧再跳回起点。

    整页只做一个动作，不再给三张卡片做 80ms 错落——大块依次飘入像 PPT
    逐条出现；换页应该是「一个面抬起来」。
    """
    animate(widget, dur=dur, delay=delay, s0=s0, s1=1.0,
            dy0=dy, dy1=0.0, a0=a0, a1=1.0,
            curve=ease_out_quint, on_done=on_done)


def prepare_entry(widget, *, s=1.0, dx=0.0, dy=0.0, rot=0.0, a=0.0, bleed=None):
    """在控件**首次绘制之前**把效果落到「入场起点」。

    对话框是先 show()、再 QTimer.singleShot(0, pop_in) 启动动画的：中间
    那一帧会以终态完整绘制一次——用户看到的是卡片先闪一下、再缩回去重新
    弹入。在 showEvent 里先把效果设成起点（a=0），首帧就是不可见的。

    bleed 与 animate() 用同一套算法，保证动画期间不会因边界不足被裁切。
    """
    try:
        eff = _effect(widget)
        if bleed is None:
            half_diag = math.hypot(widget.width(), widget.height()) / 2.0
            bleed = max(max(abs(dx), abs(dy)),
                        (max(s, 1.0) - 1.0) * half_diag) + 3.0
        eff._bleed = float(math.ceil(bleed))
        eff.invalidate()
        try:
            eff.setEnabled(True)
        except Exception:
            pass
        eff.set_values(s=s, dx=dx, dy=dy, a=a, rot=rot)
    except Exception:
        pass


def shake(widget, *, amp=10.0, dur=320, on_done=None):
    """水平抖动（错误反馈）：只改效果位移，**绝不动 geometry / pos**。

    以前是在布局管理的卡片上跑 QPropertyAnimation(card, b"pos")：布局每次
    重排都会把卡片放回原位，抖完那一下就被"拽"回去，观感是突然横跳；连点
    几次幅度还会漂。改成效果位移后控件位置始终由布局决定，抖动纯属像素。
    """
    import shiboken6
    if not shiboken6.isValid(widget) or not widget.isVisible():
        if on_done:
            on_done()
        return
    _stop(widget)
    eff = _effect(widget)
    eff.invalidate()
    eff._bleed = float(math.ceil(amp + 3.0))
    try:
        eff.setEnabled(True)
    except Exception:
        pass

    anim = QVariantAnimation(widget)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(int(dur))

    def _frame(v):
        if not shiboken6.isValid(eff):
            return
        t = float(v)
        # 衰减正弦：5 个半周期，幅度线性收到 0
        eff.set_values(dx=amp * math.sin(t * math.pi * 5.0) * (1.0 - t))

    def _done():
        if shiboken6.isValid(eff):
            eff.set_values(dx=0.0, s=1.0, dy=0.0, a=1.0, rot=0.0)
            eff._bleed = 0.0
            try:
                eff.setEnabled(False)
            except Exception:
                pass
        if on_done:
            try:
                on_done()
            except Exception:
                pass

    anim.valueChanged.connect(_frame)
    anim.finished.connect(_done)
    widget._motion_anim = anim
    _frame(0.0)
    anim.start()


def bounce(widget, *, s=1.16, dur=460, rot=0.0):
    """原地弹性脉冲（抽中结果、强调反馈）；s>1 为真正向外弹出。"""
    animate(widget, dur=dur, s0=s, s1=1.0, a0=1.0, a1=1.0,
            rot0=rot, rot1=0.0)


def stagger(widgets, *, gap=55, dy=16, s=0.94, dur=480, delay=0):
    """一组控件错落弹入。"""
    for i, w in enumerate(widgets):
        if w is not None:
            pop_in(w, dy=dy, s=s, dur=dur, delay=delay + i * gap)


def flip_text(label, text: str, *, dur=420):
    """文字翻转：压扁淡出 → 换字 → 弹性展开。"""
    if label.text() == text:
        return
    if not label.isVisible():
        label.setText(text)
        return

    def _mid():
        label.setText(text)
        # 文字已换：作废缓存再展开
        try:
            eff = label.graphicsEffect()
            if isinstance(eff, MotionEffect):
                eff.invalidate()
        except Exception:
            pass
        animate(label, dur=int(dur * 0.6), s0=0.86, s1=1.0,
                dy0=10, dy1=0.0, a0=0.0, a1=1.0)

    animate(label, dur=int(dur * 0.4), s0=1.0, s1=0.9,
            a0=1.0, a1=0.0, curve=ease_in,
            keep_effect=True, on_done=_mid)


# ---------------------------------------------------------------------------
# 光环扩散（抽中/确认时的瞬时反馈）
# ---------------------------------------------------------------------------
class BurstOverlay(QWidget):
    """覆盖在目标控件上的一次性扩散光环，自动销毁，不拦截鼠标。"""

    def __init__(self, target: QWidget, color: str, max_r: float = 160,
                 dur: int = 620):
        top = target.window()
        super().__init__(top)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._color = QColor(color)
        self._p = 0.0
        self._max_r = max_r
        c = target.mapTo(top, target.rect().center())
        # 只覆盖光环范围，且夹在父窗口内（避免边缘处被父窗口裁切）
        pad = int(max_r * 1.25)
        x = max(0, c.x() - pad)
        y = max(0, c.y() - pad)
        w = max(1, min(pad * 2, top.width() - x))
        h = max(1, min(pad * 2, top.height() - y))
        self.setGeometry(x, y, w, h)
        self._center = QPointF(c.x() - x, c.y() - y)
        self.show()
        self.raise_()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(dur)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._set)
        anim.finished.connect(self.deleteLater)
        anim.start()
        self._anim = anim

    def _set(self, v):
        self._p = float(v)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._max_r * (0.15 + 0.85 * self._p)
        a = int(120 * (1.0 - self._p) ** 1.6)
        if a <= 0:
            p.end()
            return
        c = QColor(self._color)
        c.setAlpha(a)
        p.setPen(QPen(c, max(1.0, 7.0 * (1.0 - self._p))))
        p.setBrush(QBrush())
        p.drawEllipse(self._center, r, r)
        c2 = QColor(self._color)
        c2.setAlpha(int(a * 0.35))
        p.setPen(QPen(c2, 2.0))
        p.drawEllipse(self._center, r * 0.72, r * 0.72)
        p.end()


def burst(target, color: str, **kw):
    try:
        BurstOverlay(target, color, **kw)
    except Exception:
        pass
