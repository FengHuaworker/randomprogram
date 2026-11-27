# -*- coding: utf-8 -*-
"""
随机抽号 · 项目介绍短片渲染器

纯 PIL 逐帧合成，直接管道喂给 ffmpeg（不落中间帧，省盘）。
用法：
  python tools/_video/render.py --still 9.0        # 导出单帧检查风格
  python tools/_video/render.py                    # 渲染整片
输出：video/random_picker_promo_1080p60.mp4
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "tools" / "_video" / "src"
OUT_DIR = ROOT / "video"

W, H = 1920, 1080
SS = 2                      # 超采样倍率
FW, FH = W * SS, H * SS
FPS = 60
DURATION = 45.0

# ---------------------------------------------------------------------------
# 色板：冷调墨黑 + 钢蓝，克制到只有一种强调色
# ---------------------------------------------------------------------------
INK_TOP = (10, 14, 19)
INK_BOT = (19, 26, 35)
GLOW_A = (46, 70, 92)
GLOW_B = (28, 44, 60)
TEXT = (240, 244, 248)
TEXT_DIM = (150, 162, 176)
TEXT_FAINT = (96, 108, 122)
ACCENT = (168, 196, 222)
HAIR = (66, 82, 98)

F_SERIF = r"C:\Windows\Fonts\simsun.ttc"
F_SERIFB = r"C:\Windows\Fonts\STZHONGS.TTF"
F_SANS = r"C:\Windows\Fonts\Dengl.ttf"
F_SANSB = r"C:\Windows\Fonts\Deng.ttf"
F_MONO = r"C:\Windows\Fonts\SourceCodePro-Light.ttf"
F_MONOB = r"C:\Windows\Fonts\SourceCodePro-Regular.ttf"


# ---------------------------------------------------------------------------
# 缓动
# ---------------------------------------------------------------------------
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out_expo(t):
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - pow(2, -10 * t)


def ease_in_expo(t):
    t = clamp(t)
    return 0.0 if t <= 0 else pow(2, 10 * (t - 1))


def ease_out_quint(t):
    t = clamp(t)
    return 1 - pow(1 - t, 5)


def ease_in_out_quint(t):
    t = clamp(t)
    return 16 * t ** 5 if t < 0.5 else 1 - pow(-2 * t + 2, 5) / 2


def ease_out_back(t, k=1.15):
    t = clamp(t)
    c = k + 1
    return 1 + c * pow(t - 1, 3) + k * pow(t - 1, 2)


def seg(t, a, b, ease=smooth):
    """把 t 在 [a,b] 区间映射到 0..1 再套缓动。"""
    if b <= a:
        return 1.0 if t >= b else 0.0
    return ease((t - a) / (b - a))


# ---------------------------------------------------------------------------
# 背景（一次性生成，逐帧只做轻微搬运）
# ---------------------------------------------------------------------------
def _radial(w, h, cx, cy, r, color, strength):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
    falloff = np.clip(1.0 - d, 0, 1) ** 2.2
    out = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(3):
        out[:, :, i] = color[i] * falloff * strength
    return out


BG_M = 72          # 背景预留边距，逐帧只做整数裁剪，避免重采样


def build_background():
    w, h = FW + BG_M * 2, FH + BG_M * 2
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    base = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(3):
        base[:, :, i] = (INK_TOP[i] * (1 - yy) + INK_BOT[i] * yy)

    base += _radial(w, h, w * 0.30, h * 0.18, w * 0.62, GLOW_A, 0.55)
    base += _radial(w, h, w * 0.84, h * 0.92, w * 0.55, GLOW_B, 0.75)

    # 四角压暗，画面收向中心
    vig = _radial(w, h, w * 0.5, h * 0.5, w * 0.78, (1, 1, 1), 1.0)
    v = 1.0 - 0.42 * np.clip(1.0 - vig[:, :, 0], 0, 1)
    base *= np.clip(v, 0.55, 1.0)[:, :, None]

    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def build_grain():
    rng = np.random.default_rng(20261118)
    g = rng.normal(0, 5.4, (H + 4, W + 4)).astype(np.float32)
    arr = np.clip(128 + g, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "L")


BG = None
GRAIN = None


def background_at(t, drift=1.0):
    """背景只做整数像素平移：一次生成，逐帧裁剪，代价接近零。"""
    global BG
    if BG is None:
        BG = build_background()
    dx = 26 * SS * math.sin(t * 0.07 + 0.6) * drift
    dy = 18 * SS * math.sin(t * 0.052) * drift
    left = BG_M + int(round(dx))
    top = BG_M + int(round(dy))
    return BG.crop((left, top, left + FW, top + FH))


def add_grain(img, frame_no):
    """颗粒放在 1x 上做：与成片像素一一对应，降采样也不会把它糊掉。"""
    global GRAIN
    if GRAIN is None:
        GRAIN = build_grain()
    ox = (frame_no * 7) % 5
    oy = (frame_no * 11) % 5
    g = GRAIN.crop((ox, oy, ox + W, oy + H))
    return Image.blend(img, Image.merge("RGB", (g, g, g)), 0.055)


# ---------------------------------------------------------------------------
# 文字
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1024)
def _font(path, size):
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=2048)
def text_layer(s, path, size, color, tracking=0.0):
    """渲染一行文字为 RGBA（带字距）。

    只裁掉左右空白，纵向保留完整行框 —— 这样同字号的字可以按行框对齐，
    基线天然一致（如果按 ink 包围盒裁，不同字的高矮会让一行字高低不齐）。
    """
    font = _font(path, size)
    if not s:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    widths = [font.getlength(ch) for ch in s]
    total = sum(widths) + tracking * max(0, len(s) - 1)
    asc, desc = font.getmetrics()
    pad = 8
    img = Image.new("RGBA", (int(math.ceil(total)) + pad * 2, asc + desc + pad * 2),
                    (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for ch, w in zip(s, widths):
        d.text((x, pad), ch, font=font, fill=color)
        x += w + tracking
    bbox = img.getbbox()
    if not bbox:
        return img
    left = max(0, bbox[0] - 1)
    right = min(img.width, bbox[2] + 1)
    return img.crop((left, 0, right, img.height))


def _composite_at(canvas, layer, px, py, alpha=1.0):
    """把图层贴到画布的 (px,py)，越界自动裁剪。"""
    if alpha <= 0.004:
        return
    if alpha < 0.985:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer = layer.copy()
        layer.putalpha(a)
    lw, lh = layer.size
    x0, y0 = max(0, px), max(0, py)
    x1, y1 = min(canvas.width, px + lw), min(canvas.height, py + lh)
    if x1 <= x0 or y1 <= y0:
        return
    if (x0, y0, x1, y1) == (px, py, px + lw, py + lh):
        canvas.alpha_composite(layer, (px, py))
    else:
        canvas.alpha_composite(layer.crop((x0 - px, y0 - py, x1 - px, y1 - py)), (x0, y0))


def blit(canvas, layer, x, y, alpha=1.0, anchor="lt"):
    """把 RGBA 图层贴到画布，(x,y) 为锚点；anchor 形如 lt/ct/cb/rt。"""
    if alpha <= 0.004:
        return
    lw, lh = layer.size
    px, py = x, y
    if anchor[0] == "c":
        px -= lw / 2
    elif anchor[0] == "r":
        px -= lw
    if anchor[1] == "c":
        py -= lh / 2
    elif anchor[1] == "b":
        py -= lh
    _composite_at(canvas, layer, int(round(px)), int(round(py)), alpha)


# ---------------------------------------------------------------------------
# 透视贴图（卡片带 3D 倾斜）
# ---------------------------------------------------------------------------
def _persp_coeffs(src, dst):
    """求 PIL PERSPECTIVE 系数：把输出点 dst 映回输入点 src。"""
    A, B = [], []
    for (xd, yd), (xs, ys) in zip(dst, src):
        A.append([xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd])
        B.append(xs)
        A.append([0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd])
        B.append(ys)
    res = np.linalg.solve(np.array(A, dtype=np.float64), np.array(B, dtype=np.float64))
    return tuple(res.tolist())


def quad_of(cx, cy, w, h, rot=0.0, skew=0.0):
    """生成四个角点：绕中心旋转 rot(度)，skew 为透视收窄量(0~0.3)。"""
    r = math.radians(rot)
    cos_r, sin_r = math.cos(r), math.sin(r)
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = sx * w / 2, sy * h / 2
        # 左右两侧分别收窄，制造绕 Y 轴旋转的观感
        x *= (1 - skew) if sx < 0 else (1 + skew)
        y *= (1 - skew) if sx < 0 else (1 + skew)
        pts.append((cx + x * cos_r - y * sin_r, cy + x * sin_r + y * cos_r))
    return pts


def place_quad(canvas, img, quad, alpha=1.0):
    if alpha <= 0.004:
        return
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    fx0, fy0, fx1, fy1 = min(xs), min(ys), max(xs), max(ys)

    # 无旋转、无透视时，四角就是矩形：直接合成，跳过一次昂贵的重采样。
    # 静止镜头占绝大多数帧，这一条能把单帧成本砍掉一大半。
    if (abs(quad[0][0] - fx0) < 1 and abs(quad[0][1] - fy0) < 1
            and abs(quad[1][0] - fx1) < 1 and abs(quad[1][1] - fy0) < 1
            and abs(quad[2][0] - fx1) < 1 and abs(quad[2][1] - fy1) < 1
            and abs(quad[3][0] - fx0) < 1 and abs(quad[3][1] - fy1) < 1
            and abs((fx1 - fx0) - img.width) < 2 and abs((fy1 - fy0) - img.height) < 2):
        _composite_at(canvas, img, int(round(fx0)), int(round(fy0)), alpha)
        return

    bx0, by0 = int(math.floor(fx0)), int(math.floor(fy0))
    bx1, by1 = int(math.ceil(fx1)), int(math.ceil(fy1))
    bw, bh = bx1 - bx0, by1 - by0
    if bw <= 1 or bh <= 1:
        return

    src = [(0, 0), (img.width, 0), (img.width, img.height), (0, img.height)]
    dst = [(p[0] - bx0, p[1] - by0) for p in quad]
    coeffs = _persp_coeffs(src, dst)
    out = img.transform((bw, bh), Image.Transform.PERSPECTIVE, coeffs,
                        resample=Image.Resampling.BILINEAR)
    if alpha < 0.996:
        a = out.getchannel("A").point(lambda v: int(v * alpha))
        out.putalpha(a)
    x0, y0 = max(0, bx0), max(0, by0)
    x1, y1 = min(FW, bx1), min(FH, by1)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(out.crop((x0 - bx0, y0 - by0, x1 - bx0, y1 - by0)), (x0, y0))


# ---------------------------------------------------------------------------
# 卡片：截图 + 描边 + 投影
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def card_asset(name, width_px, radius=16, border=True):
    """返回裁圆角 + 描边的截图卡片（不含阴影）。"""
    path = SRC / f"{name}.png"
    img = Image.open(path).convert("RGB")
    h = int(round(img.height * width_px / img.width))
    img = img.resize((width_px, h), Image.Resampling.LANCZOS).convert("RGBA")

    mask = Image.new("L", (width_px, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width_px - 1, h - 1],
                                           radius=radius, fill=255)
    img.putalpha(mask)

    if border:
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, width_px - 1, h - 1], radius=radius,
                            outline=(255, 255, 255, 44), width=max(1, width_px // 700))
    return img


@lru_cache(maxsize=32)
def shadow_asset(width_px, height_px, radius=16, blur=34, opacity=170):
    pad = blur * 3
    w, h = width_px + pad * 2, height_px + pad * 2
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).rounded_rectangle(
        [pad, pad, pad + width_px, pad + height_px], radius=radius, fill=opacity)
    img = img.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.putalpha(img)
    return out, pad


@lru_cache(maxsize=24)
def card_bundle(name, width_px, radius=16, shadow=True):
    """卡片 + 投影烘焙成一张图：每帧只合成一次，省掉半张画布的搬运。"""
    card = card_asset(name, width_px, radius)
    w, h = card.size
    if not shadow:
        return card, 0
    sh, pad = shadow_asset(w, h, radius)
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 12 * SS))       # 投影略微下移
    out.alpha_composite(card, (pad, pad))       # 卡片居中，外层包围盒对称
    return out, pad


def draw_card(canvas, name, cx, cy, width_px, alpha=1.0, rot=0.0, skew=0.0,
              shadow=True, radius=16):
    img, pad = card_bundle(name, width_px, radius, shadow)
    place_quad(canvas, img, quad_of(cx, cy, img.width, img.height, rot, skew), alpha)


# ---------------------------------------------------------------------------
# 装饰
# ---------------------------------------------------------------------------
def hairline(canvas, x0, y0, x1, y1, alpha, color=HAIR, width=1):
    if alpha <= 0.004:
        return
    pad = width + 2
    bx0 = int(math.floor(min(x0, x1))) - pad
    by0 = int(math.floor(min(y0, y1))) - pad
    bx1 = int(math.ceil(max(x0, x1))) + pad
    by1 = int(math.ceil(max(y0, y1))) + pad
    tile = Image.new("RGBA", (bx1 - bx0, by1 - by0), (0, 0, 0, 0))
    ImageDraw.Draw(tile).line([(x0 - bx0, y0 - by0), (x1 - bx0, y1 - by0)],
                              fill=color + (int(255 * alpha),), width=max(1, width))
    _composite_at(canvas, tile, bx0, by0)


def ring(canvas, cx, cy, r, alpha, color=ACCENT, width=2):
    if alpha <= 0.004 or r <= 0:
        return
    pad = width + 2
    side = int(r * 2) + pad * 2 + 2
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ImageDraw.Draw(tile).ellipse([pad, pad, side - pad - 1, side - pad - 1],
                                 outline=color + (int(255 * alpha),), width=width)
    _composite_at(canvas, tile, int(round(cx - side / 2)), int(round(cy - side / 2)))


def arc(canvas, cx, cy, r, a0, a1, alpha, color=ACCENT, width=2):
    """画一段圆弧，用于抽号定格时的描边。"""
    if alpha <= 0.004 or r <= 0 or a1 <= a0:
        return
    pad = width + 3
    side = int(r * 2) + pad * 2 + 2
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    c = side / 2
    ImageDraw.Draw(tile).arc([c - r, c - r, c + r, c + r], a0, a1,
                             fill=color + (int(255 * alpha),), width=width)
    _composite_at(canvas, tile, int(round(cx - c)), int(round(cy - c)))


@lru_cache(maxsize=16)
def _blob(w, h, color, blur):
    """预模糊的实心椭圆；每帧只改透明度，不重复做高斯模糊。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, w - 1, h - 1], fill=color + (255,))
    return img.filter(ImageFilter.GaussianBlur(blur))


def glow_dot(canvas, cx, cy, r, alpha, color=ACCENT):
    if alpha <= 0.004:
        return
    s = int(r * 2)
    img = _blob(s, s, color, r * 0.35)
    place_quad(canvas, img, quad_of(cx, cy, s, s), alpha)


def soft_glow(canvas, cx, cy, rx, ry, alpha, color=GLOW_A):
    """椭圆柔光，用来把主体从背景里托起来。"""
    if alpha <= 0.004:
        return
    w, h = int(rx * 2), int(ry * 2)
    img = _blob(w, h, color, min(rx, ry) * 0.5)
    place_quad(canvas, img, quad_of(cx, cy, w, h), alpha)


# ---------------------------------------------------------------------------
# 场景
# ---------------------------------------------------------------------------
TITLE = "随机抽号"
SUBTITLE = "课堂随机抽号 · 单文件 · 免安装"
URL = "github.com/FengHuaworker/randomprogram"


def scene_intro(canvas, t):
    """片头：标题入场"""
    cx = FW / 2
    base_y = FH * 0.465

    # 顶部小标
    a = seg(t, 0.35, 1.25)
    lab = text_layer("RANDOM  PICKER  ·  V1.1.0", F_MONO, 26 * SS, TEXT_FAINT, 6 * SS)
    blit(canvas, lab, cx, FH * 0.235, a * 0.9, "ct")

    # 主标题：逐字上浮 + 字距收紧
    chars = list(TITLE)
    size = 152 * SS
    tracking = (0.26 - 0.11 * seg(t, 0.45, 1.9, ease_out_expo)) * size
    layers = [text_layer(ch, F_SERIF, size, TEXT) for ch in chars]
    gap = 16 * SS
    total = sum(l.width for l in layers) + gap * (len(layers) - 1) + tracking * (len(layers) - 1)
    x = cx - total / 2
    for i, lay in enumerate(layers):
        p = seg(t, 0.45 + i * 0.11, 1.75 + i * 0.11, ease_out_expo)
        dy = (1 - p) * 46 * SS
        blit(canvas, lay, x, base_y + dy, p, "lc")
        x += lay.width + gap + tracking

    # 副标题
    a2 = seg(t, 1.55, 2.5, ease_out_expo)
    sub = text_layer(SUBTITLE, F_SANS, 40 * SS, TEXT_DIM, 5 * SS)
    blit(canvas, sub, cx, base_y + 96 * SS, a2 * 0.95, "ct")

    # 上下细线
    lw = ease_out_expo(seg(t, 0.8, 2.2)) * 330 * SS
    hairline(canvas, cx - lw, base_y + 176 * SS, cx + lw, base_y + 176 * SS,
             seg(t, 0.8, 2.2) * 0.7)
    lw2 = ease_out_expo(seg(t, 1.0, 2.3)) * 200 * SS
    hairline(canvas, cx - lw2, FH * 0.170, cx + lw2, FH * 0.170, seg(t, 1.0, 2.3) * 0.45)

    # 呼吸光点
    pa = seg(t, 2.3, 3.4) * (0.55 + 0.45 * math.sin(t * 2.2))
    glow_dot(canvas, cx, base_y - 112 * SS, 8 * SS, pa * 0.8)


def scene_hero(canvas, t):
    """主界面：只放一张，靠缓慢推近和说明行撑住"""
    cx = FW / 2
    cy = FH * 0.527

    p = seg(t, 0.0, 1.9, ease_out_expo)
    # 宽度量化到 8px 台阶：入场 1.9s 内只生成十来个尺寸，避免每帧重算卡片
    width = int(1240 * SS * (0.972 + 0.028 * p) / 8) * 8
    rot = -1.7 * (1 - p)
    skew = 0.045 * (1 - p)
    alpha = seg(t, 0.0, 0.9)
    # 入场后极慢的上下浮动，画面不会完全定住（整数位移，不触发重采样）
    bob = 5 * SS * math.sin(t * 0.52) * p

    soft_glow(canvas, cx, cy + 200 * SS, 720 * SS, 140 * SS, alpha * 0.34)

    draw_card(canvas, "main_draw", cx, cy + (1 - p) * 42 * SS + bob, width,
              alpha=alpha, rot=rot, skew=skew, radius=14 * SS)

    # 顶部小标
    a0 = seg(t, 0.5, 1.4, ease_out_expo)
    kick = text_layer("01   ·   抽  号", F_SANS, 26 * SS, TEXT_FAINT, 5 * SS)
    blit(canvas, kick, cx, FH * 0.082, a0 * 0.85, "ct")

    # 底部一行说明
    a1 = seg(t, 1.8, 2.8, ease_out_expo)
    cap = text_layer("翻号  →  弹性定格  →  自动记录", F_SANS, 30 * SS, TEXT_DIM, 3 * SS)
    blit(canvas, cap, cx, FH * 0.952, a1 * 0.9, "ct")

    lw = ease_out_expo(seg(t, 1.8, 2.9)) * 250 * SS
    hairline(canvas, cx - lw, FH * 0.910, cx + lw, FH * 0.910, a1 * 0.28)


@lru_cache(maxsize=8)
def reel_strip(target, size, color, reps=12):
    """竖直数字条。第 0 行就是落定数字，窗口向上滑即倒数。"""
    font = _font(F_SERIF, size)
    asc, desc = font.getmetrics()
    lh = asc + desc
    w = int(font.getlength("8")) + int(size * 0.10)
    img = Image.new("RGBA", (w, lh * reps), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for k in range(reps):
        ch = str((target - k) % 10)
        d.text(((w - font.getlength(ch)) / 2, k * lh), ch, font=font, fill=color)
    return img, lh, w


def _reel_offset(t, lh, span=9.0, v0=4.2, dec=2.0, t0=0.25, dec_t=0.55):
    """剩余行数：匀速快滚，最后两行减速压住 —— 老虎机的节奏。

    匀速段速度恒定，末段三次减速，落定前能看清最后两个数字再停。
    """
    if t <= t0:
        return span * lh
    tb = t0 + max(0.0, span - dec) / v0
    if t < tb:
        return (span - v0 * (t - t0)) * lh
    u = clamp((t - tb) / dec_t)
    return dec * lh * (1.0 - u) ** 3


def scene_roll(canvas, t):
    """抽号瞬间：数字滚轮落定"""
    cx = FW / 2
    size = 300 * SS
    target = "03"
    settle0, settle1 = 2.50, 2.65          # 两位数字错峰落定

    # 顶部小标
    a0 = seg(t, 0.15, 0.95, ease_out_expo)
    lab = text_layer("本  次  抽  中", F_SANS, 27 * SS, TEXT_FAINT, 6 * SS)
    blit(canvas, lab, cx, FH * 0.205, a0 * 0.85, "ct")

    strip0, lh, dw = reel_strip(int(target[0]), size, TEXT)
    strip1, _, _ = reel_strip(int(target[1]), size, TEXT)
    gap = 34 * SS
    total_w = dw * 2 + gap
    x0 = cx - total_w / 2
    y_mid = FH * 0.455

    # 落定后 0.35s 内的轻微回弹
    def recoil(ts):
        if ts < 0.35:
            return 0.0
        d = ts - 0.35
        return -7 * SS * math.exp(-d * 7.0) * math.sin(d * 26.0)

    locked = t >= settle1
    for i, (strip, st) in enumerate(((strip0, settle0), (strip1, settle1))):
        # 第二位数字晚 0.15s 起步，落定时就有一前一后的“咔、咔”感
        tt = t - i * 0.15
        if t < st:
            off = _reel_offset(tt, lh, 9.0, 4.2, 2.0, 0.25)
            prev = _reel_offset(max(0.0, tt - 1 / 240), lh, 9.0, 4.2, 2.0, 0.25)
            v = (off - prev) * 240
        else:
            off = 0.0
            v = 0.0

        # 窗口在条带上滑到 off 处；条带被裁出来贴回固定位置，
        # 数字在窗口里的相对位置自然就变了 —— 这就是滚动。
        y0 = int(round(off))
        pad = int(22 * SS)
        c0 = max(0, y0 - pad)
        c1 = min(strip.height, y0 + lh + pad)
        if c1 <= c0:
            continue
        crop = strip.crop((0, c0, strip.width, c1))
        blur = min(abs(v) / 155.0, 20 * SS)
        if blur > 0.5:
            crop = crop.filter(ImageFilter.GaussianBlur(blur))
        crop = crop.crop((0, y0 - c0, crop.width, y0 - c0 + lh))

        dy = recoil(t - st) if t >= st else 0
        _composite_at(canvas, crop, int(round(x0 + i * (dw + gap))),
                      int(round(y_mid - lh / 2 + dy)))

    # 定格瞬间：光环向外扩散，收在姓名之上
    if locked:
        u = clamp((t - settle1) / 0.85)
        ring(canvas, cx, y_mid, 200 * SS + 40 * SS * ease_out_expo(u),
             (1 - u) * 0.42, ACCENT, width=max(1, int(1.4 * SS)))

    # 姓名
    a2 = seg(t, settle1 + 0.10, settle1 + 0.92, ease_out_expo)
    if a2 > 0.004:
        nm = text_layer("张小强", F_SERIF, 58 * SS, TEXT, 12 * SS)
        blit(canvas, nm, cx, y_mid + 270 * SS, a2, "ct")

    # 底部说明
    a3 = seg(t, 3.5, 4.4)
    cap = text_layer("每秒 60 次翻号  ·  落定回弹  ·  自动记录", F_SANS, 28 * SS,
                     TEXT_DIM, 3 * SS)
    blit(canvas, cap, cx, FH * 0.878, a3 * 0.92, "ct")


def scene_gallery(canvas, t):
    """三张功能页并排入场"""
    items = [
        ("history", "抽号记录", "轮次视图 · 删除单条 · 导出 TXT"),
        ("stats", "概率统计", "占比条自绘 · 按最高者归一"),
        ("shield", "屏蔽管理", "长期 / 短期 / 冷却"),
    ]
    cx = FW / 2
    cy = FH * 0.475
    w = int(590 * SS)

    for i, (name, title, desc) in enumerate(items):
        p = seg(t, 0.55 + i * 0.26, 1.95 + i * 0.26, ease_out_expo)
        if p <= 0.004:
            continue
        dx = (i - 1) * 618 * SS
        dy = (1 - p) * 86 * SS
        rot = (i - 1) * 1.8 * (1 - p)
        draw_card(canvas, name, cx + dx, cy + dy, w, p, rot=rot, radius=11 * SS)

        a = seg(t, 1.45 + i * 0.26, 2.35 + i * 0.26)
        t1 = text_layer(title, F_SANSB, 29 * SS, TEXT, 3 * SS)
        t2 = text_layer(desc, F_SANS, 20 * SS, TEXT_FAINT, 1 * SS)
        by = cy + int(w * 1600 / 2560) / 2 + 40 * SS
        blit(canvas, t1, cx + dx, by, a, "ct")
        blit(canvas, t2, cx + dx, by + 44 * SS, a * 0.85, "ct")

    # 顶部小标题
    a = seg(t, 0.2, 1.1, ease_out_expo)
    lab = text_layer("记录  ·  统计  ·  屏蔽", F_SANS, 29 * SS, TEXT_DIM, 9 * SS)
    blit(canvas, lab, cx, FH * 0.145, a * 0.75, "ct")

    a3 = seg(t, 2.3, 3.2)
    foot = text_layer("五个页面，全部离线运行", F_SANS, 24 * SS, TEXT_FAINT, 4 * SS)
    blit(canvas, foot, cx, FH * 0.915, a3 * 0.78, "ct")


FEATURES = [
    ("01", "多班级独立数据", "名单、屏蔽、防重、记录各自隔离，切换即时生效"),
    ("02", "防重 24 小时", "窗口可配、可关闭，抽过的人自动进冷却"),
    ("03", "屏蔽三态", "长期 / 短期次日解除 / 冷却，摇号池实时统计"),
    ("04", "名单随手导入", "TXT 拖入，内置编辑器增删排序"),
]


def scene_features(canvas, t):
    """特性矩阵：四点两列"""
    cx = FW / 2
    a0 = seg(t, 0.15, 1.0, ease_out_expo)
    lab = text_layer("为课堂节奏设计", F_SANSB, 30 * SS, TEXT_DIM, 6 * SS)
    blit(canvas, lab, cx, FH * 0.155, a0 * 0.8, "ct")

    col_x = [FW * 0.205, FW * 0.688]
    row_y = [FH * 0.348, FH * 0.648]
    for i, (num, title, desc) in enumerate(FEATURES):
        c, r = i % 2, i // 2
        p = seg(t, 0.45 + i * 0.24, 1.75 + i * 0.24, ease_out_expo)
        if p <= 0.004:
            continue
        x, y = col_x[c], row_y[r]
        dy = (1 - p) * 30 * SS

        n = text_layer(num, F_MONO, 22 * SS, ACCENT)
        blit(canvas, n, x - 92 * SS, y + dy - 6 * SS, p * 0.75, "rt")
        hairline(canvas, x - 82 * SS, y + dy + 6 * SS, x - 82 * SS, y + dy + 62 * SS,
                 p * 0.35)

        t1 = text_layer(title, F_SANSB, 44 * SS, TEXT, 3 * SS)
        blit(canvas, t1, x, y + dy, p, "lt")
        t2 = text_layer(desc, F_SANS, 25 * SS, TEXT_FAINT, 1 * SS)
        blit(canvas, t2, x, y + dy + 64 * SS, p * 0.9, "lt")

    # 两行之间一道极淡的分隔，给四宫格一个隐性格栅
    g = seg(t, 0.35, 1.5)
    gw = ease_out_expo(g) * FW * 0.315
    hairline(canvas, cx - gw, FH * 0.535, cx + gw, FH * 0.535, g * 0.30)


def scene_engine(canvas, t):
    """工程质感：三个大数字"""
    cx = FW / 2
    a = seg(t, 0.1, 1.0, ease_out_expo)
    lab = text_layer("ENGINEERING", F_MONO, 24 * SS, TEXT_FAINT, 9 * SS)
    blit(canvas, lab, cx, FH * 0.185, a * 0.85, "ct")

    # 三个大数字
    stats = [("45", "MB", "单文件，双击即用"), ("0", "依赖", "不装 Python、不写注册表"), ("60", "FPS", "自绘动效，全程不掉帧")]
    xs = [FW * 0.235, FW * 0.5, FW * 0.765]
    for i, (num, unit, desc) in enumerate(stats):
        p = seg(t, 0.45 + i * 0.22, 1.6 + i * 0.22, ease_out_expo)
        if p <= 0.004:
            continue
        x = xs[i]
        dy = (1 - p) * 26 * SS
        n = text_layer(num, F_SERIF, 132 * SS, TEXT)
        blit(canvas, n, x, FH * 0.40 + dy, p, "cb")
        u = text_layer(unit, F_SANS, 30 * SS, TEXT_DIM, 2 * SS)
        blit(canvas, u, x, FH * 0.40 + dy + 16 * SS, p * 0.9, "ct")
        d = text_layer(desc, F_SANS, 23 * SS, TEXT_FAINT, 1 * SS)
        blit(canvas, d, x, FH * 0.545 + dy, p * 0.85, "ct")

    # 底部技术行
    a2 = seg(t, 1.5, 2.4)
    tech = text_layer("PySide6  ·  Qt 6  ·  Python 3  ·  单文件打包", F_SANS, 26 * SS, TEXT_DIM, 3 * SS)
    blit(canvas, tech, cx, FH * 0.70, a2 * 0.8, "ct")
    lw = ease_out_expo(seg(t, 1.5, 2.6)) * 300 * SS
    hairline(canvas, cx - lw, FH * 0.765, cx + lw, FH * 0.765, a2 * 0.4)


def scene_outro(canvas, t):
    """收尾：标记、地址、版本"""
    cx = FW / 2
    cy = FH * 0.468

    p = seg(t, 0.15, 1.6, ease_out_expo)
    # 标记：圆角方框内的两个字
    s = 118 * SS
    box = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=30 * SS, outline=ACCENT + (200,),
                        width=max(2, 2 * SS))
    ch1 = text_layer("抽", F_SERIF, int(s * 0.46), TEXT)
    blit(box, ch1, s / 2, s / 2 + 2 * SS, 1.0, "cc")
    place_quad(canvas, box, quad_of(cx, cy - 96 * SS + (1 - p) * 22 * SS, s, s,
                                    rot=-3 * (1 - p)), p)

    a1 = seg(t, 0.55, 1.6, ease_out_expo)
    t1 = text_layer(TITLE, F_SERIF, 74 * SS, TEXT, 6 * SS)
    blit(canvas, t1, cx, cy + 44 * SS, a1, "ct")

    a2 = seg(t, 0.95, 1.9)
    u = text_layer(URL, F_MONO, 30 * SS, ACCENT, 1 * SS)
    blit(canvas, u, cx, cy + 146 * SS, a2 * 0.9, "ct")

    a3 = seg(t, 1.25, 2.2)
    tag = text_layer("v1.1.0 · 2026", F_MONO, 22 * SS, TEXT_FAINT, 3 * SS)
    blit(canvas, tag, cx, cy + 216 * SS, a3 * 0.75, "ct")

    lw = ease_out_expo(seg(t, 0.85, 2.3)) * 250 * SS
    hairline(canvas, cx - lw, cy + 190 * SS, cx + lw, cy + 190 * SS, a3 * 0.25)


# (开始, 结束, 绘制, 淡入, 淡出)
SCENES = [
    (0.0, 6.0, scene_intro, 0.0, 0.22),
    (6.0, 13.2, scene_hero, 0.22, 0.22),
    (13.2, 19.6, scene_roll, 0.22, 0.22),
    (19.6, 26.6, scene_gallery, 0.22, 0.22),
    (26.6, 33.0, scene_features, 0.22, 0.22),
    (33.0, 38.2, scene_engine, 0.22, 0.22),
    (38.2, DURATION, scene_outro, 0.22, 1.1),
]


def render_frame(t, frame_no):
    img = background_at(t)

    # 文字页与截图页叠化会互相压脏，所以每场之间用极短的压黑换气（0.22s），
    # 既不糊在一起，也不会像长淡出那样出现空画面。
    active = []
    for (s, e, fn, fin, fout) in SCENES:
        start = s
        if start - 0.01 <= t < e + 0.01:
            active.append((start, e, fn, fin, fout))

    for (start, e, fn, fin, fout) in active:
        a_in = smooth(clamp((t - start) / fin)) if fin > 0 else 1.0
        a_out = smooth(clamp((e - t) / fout)) if fout > 0 else 1.0
        a = a_in * a_out
        if a <= 0.004:
            continue
        # 只有一个场景且完全不透明时直接画在背景上：省掉一次整幅合成
        if len(active) == 1 and a >= 0.985:
            fn(img, t - start)
            continue
        layer = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
        fn(layer, t - start)
        if a < 0.985:
            al = layer.getchannel("A").point(lambda v: int(v * a))
            layer.putalpha(al)
        img.alpha_composite(layer)

    small = img.reduce(SS)
    return add_grain(small.convert("RGB"), frame_no)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--still", type=float, default=None, help="只导出该时刻的单帧")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=DURATION)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.still is not None:
        img = render_frame(args.still, int(args.still * FPS))
        p = Path(args.out) if args.out else OUT_DIR / f"still_{args.still:05.2f}.png"
        img.save(p)
        print("saved:", p, img.size)
        return

    out = Path(args.out) if args.out else OUT_DIR / "random_picker_promo_1080p60.mp4"
    total = int((args.t1 - args.t0) * FPS)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    import time
    t_start = time.perf_counter()
    for i in range(total):
        t = args.t0 + i / FPS
        frame = render_frame(t, i)
        proc.stdin.write(frame.tobytes())
        if i % 60 == 0:
            el = time.perf_counter() - t_start
            fps = (i + 1) / max(el, 1e-6)
            eta = (total - i) / max(fps, 1e-6)
            print(f"  {i}/{total}  {fps:.1f} fps  ETA {eta/60:.1f} min", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done ->", out, f"({out.stat().st_size/1e6:.1f} MB)" if out.exists() else "")


if __name__ == "__main__":
    main()
