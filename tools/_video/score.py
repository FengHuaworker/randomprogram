# -*- coding: utf-8 -*-
"""
随机抽号 · 介绍短片配乐（程序合成）

无采样、无版权素材，全部用正弦叠层与滤波噪声生成：
  · 低频 pad 铺底，A 小调，和声每 6~7 秒换一次，跟画面分段对齐
  · 极轻的心跳脉冲，给节奏但不抢戏
  · 抽号段：滚轮咔哒 + 上行 riser + 落定重音（对齐数字定格）
  · 每场切入一记很轻的钟，充当章节感

输出：video/score.wav（48kHz / 16bit / 立体声）
"""

from __future__ import annotations

from pathlib import Path
import wave

import numpy as np
from scipy import signal

SR = 48000
DUR = 45.0
N = int(SR * DUR)
HERE = Path(__file__).resolve().parent.parent.parent
OUT = HERE / "video" / "score.wav"

rng = np.random.default_rng(20261118)

L = np.zeros(N, dtype=np.float64)
R = np.zeros(N, dtype=np.float64)


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def add(sig, at, pan=0.0, gain=1.0):
    """把单声道信号按等功率声像混入总线。"""
    i = int(at * SR)
    if i >= N:
        return
    n = min(len(sig), N - i)
    if n <= 0:
        return
    th = (pan + 1) * np.pi / 4
    L[i:i + n] += sig[:n] * np.cos(th) * gain
    R[i:i + n] += sig[:n] * np.sin(th) * gain


def env_adsr(n, a, d, s, r):
    """起音 / 衰减 / 保持 / 释放，用插值做，末尾必归零。"""
    dur = n / SR
    r = min(r, dur * 0.8)
    xs = [0.0, a, a + d, max(a + d, dur - r), dur]
    ys = [0.0, 1.0, s, s, 0.0]
    e = np.interp(np.arange(n) / SR, xs, ys)
    return e ** 1.35


def band_noise(n, lo, hi, order=2):
    """带通白噪声，用来做空气感与 riser。"""
    x = rng.normal(0, 1, n)
    sos = signal.butter(order, [lo / (SR / 2), min(hi, SR / 2 - 200) / (SR / 2)],
                        btype="band", output="sos")
    return signal.sosfilt(sos, x)


# ---------------------------------------------------------------------------
# 音色
# ---------------------------------------------------------------------------
def pad_voice(f, dur, amp=0.10, a=1.9, r=2.6):
    """三层微失谐正弦 + 泛音塔，柔和的弦垫音色。

    泛音给到第 6 次、再加一层两倍频的 shimmer，
    否则整段只剩低频，听起来发闷。
    """
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det, w in ((-0.0050, 0.55), (0.0, 0.75), (0.0048, 0.55)):
        ff = f * (1 + det)
        out += w * np.sin(2 * np.pi * ff * t + rng.random() * 6.28)
        out += 0.30 * w * np.sin(2 * np.pi * ff * 2 * t + rng.random() * 6.28)
        out += 0.13 * w * np.sin(2 * np.pi * ff * 3 * t)
        out += 0.07 * w * np.sin(2 * np.pi * ff * 4 * t)
        out += 0.04 * w * np.sin(2 * np.pi * ff * 5 * t)
        out += 0.025 * w * np.sin(2 * np.pi * ff * 6 * t)
    # 两倍频的微弱 shimmer + 慢速颤动，给中高频一点空气
    out += 0.020 * np.sin(2 * np.pi * f * 4 * t + 0.7 * np.sin(2 * np.pi * 0.21 * t))
    lfo = 1.0 + 0.06 * np.sin(2 * np.pi * 0.13 * t + rng.random() * 6.28)
    return out * env_adsr(n, a, 0.8, 0.88, r) * lfo * amp


def sub_voice(f, dur, amp=0.16):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * env_adsr(n, 1.4, 0.6, 0.9, 2.2) * amp


def bell(f, dur=3.0, amp=0.12):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.exp(-t / (dur * 0.28)) * np.minimum(1.0, t / 0.012)
    s = (np.sin(2 * np.pi * f * t)
         + 0.34 * np.sin(2 * np.pi * f * 2.01 * t)
         + 0.12 * np.sin(2 * np.pi * f * 2.76 * t))
    return s * env * amp


def tick(amp=0.05):
    """滚轮咔哒：极短的噪声 + 高频点。"""
    n = int(0.028 * SR)
    t = np.arange(n) / SR
    body = band_noise(n, 1800, 6500) * np.exp(-t / 0.004)
    ping = np.sin(2 * np.pi * 2600 * t) * np.exp(-t / 0.006)
    return (body * 0.7 + ping * 0.5) * np.minimum(1.0, t / 0.0015) * amp


def thump(f=55, dur=0.42, amp=0.10):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.exp(-t / 0.075) * np.minimum(1.0, t / 0.008)
    return np.sin(2 * np.pi * f * (1 - 0.25 * t / dur) * t) * env * amp


def impact(amp=0.30):
    """落定重音：低频下坠 + 短促噪声。"""
    dur = 1.6
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 96 * np.exp(-t / 0.55) + 42
    sweep = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.45)
    noise = band_noise(n, 300, 3200) * np.exp(-t / 0.09) * 0.45
    return (sweep + noise) * amp


# ---------------------------------------------------------------------------
# 编曲：和声与画面分段对齐
# ---------------------------------------------------------------------------
# (起始, 结束, MIDI 音高列表)
# 低音留给 sub，pad 一律放在中音区（130~520Hz），否则整段会糊在低频里
CHORDS = [
    (0.0, 6.0, 45, [57, 64, 71, 72], 0.70),            # Am(add9)  片头
    (6.0, 13.2, 41, [53, 60, 64, 69, 72], 0.85),       # Fmaj7     主界面
    (13.2, 19.6, 43, [55, 62, 67, 71], 0.80),          # G         抽号
    (19.6, 26.6, 38, [50, 57, 60, 64, 65], 0.92),      # Dm9       功能页
    (26.6, 33.0, 41, [53, 60, 64, 67, 71], 0.96),      # Fmaj9     特性
    (33.0, 38.2, 40, [52, 59, 62, 67], 0.84),          # Em7       工程
    (38.2, 45.0, 45, [57, 64, 69, 71, 72], 1.00),      # Am(add9)  收尾
]

for ci, (s, e, root, notes, dyn) in enumerate(CHORDS):
    # 提前 1.2 秒进入：慢起音正好跨过画面切点，交接处才不会有空档
    t0 = max(0.0, s - 1.2)
    dur = e - t0 + 1.1
    s = t0
    for i, m in enumerate(notes):
        f = midi(m)
        # 声部越靠上声像越开，低音居中
        pan = (i / max(1, len(notes) - 1) - 0.5) * 0.9
        amp = 0.062 * dyn
        add(pad_voice(f, dur, amp), s, pan, 1.0)
        # 左侧再叠一层延时，制造宽度
        if i >= 2:
            add(pad_voice(f * 1.0007, dur, amp * 0.45), s + 0.011, -pan * 0.8)
    add(sub_voice(midi(root - 12), dur, 0.085 * dyn), s, 0.0)

# 空气层：极轻的高频噪声，随段落起伏
air = band_noise(N, 1200, 9000)
tt = np.arange(N) / SR
air_env = (0.55 + 0.45 * np.sin(2 * np.pi * 0.055 * tt - 1.2))
air_env *= np.interp(tt, [0, 3, 40, 45], [0, 1, 1, 0])
add(air * air_env * 0.024, 0.0, 0.0)
add(np.roll(air, 977) * air_env * 0.019, 0.0, 0.0)

# 稀疏的高音钟：每隔几秒落一颗，给中高频一点亮光，也避免长音发闷
bt = 8.0
k = 0
while bt < 36.5:
    cur = next((c for c in CHORDS if c[0] <= bt < c[1]), CHORDS[-1])
    notes = cur[3]
    m = notes[1 if k % 2 else -1] + 24
    add(bell(midi(m), 2.8, 0.032), bt, 0.35 if k % 2 else -0.35)
    bt += 3.2
    k += 1

# 心跳：从主界面开始，2.4 秒一次，收尾前停
b = 7.0
while b < 41.0:
    add(thump(52, 0.5, 0.052), b, 0.0)
    add(thump(49, 0.35, 0.024), b + 0.30, 0.0)
    b += 2.4

# 章节钟声：每场切入后 0.06s，很轻
for at, m, g in ((6.06, 81, 0.075), (19.66, 76, 0.070), (26.66, 84, 0.065),
                 (33.06, 79, 0.060), (38.26, 81, 0.080)):
    add(bell(midi(m), 3.4, g), at, 0.22)
    add(bell(midi(m + 12), 2.2, g * 0.35), at + 0.012, -0.25)

# 抽号：滚轮咔哒（13.45-15.55 渐强）+ riser（15.4-16.5）+ 落定重音（16.5）
k = 13.45
i = 0
while k < 15.55:
    g = 0.016 + 0.05 * ((k - 13.45) / 2.1) ** 1.6
    add(tick(g), k, 0.18 if i % 2 else -0.18)
    k += 0.083
    i += 1

n_r = int(1.1 * SR)
t_r = np.arange(n_r) / SR
riser = np.sin(2 * np.pi * np.cumsum(210 * (2 ** (t_r / 1.1 * 2.4))) / SR)
riser *= (t_r / 1.1) ** 2.2
add(riser * 0.055, 15.4, 0.0)
add(band_noise(n_r, 900, 7000) * (t_r / 1.1) ** 2.4 * 0.05, 15.4, 0.0)

add(impact(0.26), 16.50, 0.0)
add(bell(midi(88), 2.8, 0.10), 16.51, 0.15)
add(bell(midi(93), 1.8, 0.055), 16.53, -0.2)

# 收尾：一记高音钟，然后自然衰减
add(bell(midi(81), 5.0, 0.085), 41.6, 0.0)
add(bell(midi(76), 4.4, 0.045), 41.62, 0.3)

# ---------------------------------------------------------------------------
# 总线处理
# ---------------------------------------------------------------------------
mix = np.stack([L, R], axis=1)

# 轻柔的高频滚降，去掉合成器的毛刺
sos = signal.butter(2, 16000 / (SR / 2), btype="low", output="sos")
mix = signal.sosfilt(sos, mix, axis=0)

# 首尾淡入淡出
fade_in = int(0.35 * SR)
fade_out = int(2.6 * SR)
mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None] ** 1.5
mix[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.8

# 峰值归一到 -1.2 dBFS，留足余量
peak = float(np.max(np.abs(mix)))
mix *= 0.87 / max(peak, 1e-9)

pcm = np.clip(mix * 32767.0, -32768, 32767).astype("<i2")
OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

rms = float(np.sqrt(np.mean(mix ** 2)))
print(f"saved: {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)")
print(f"峰值 {20*np.log10(peak*0.87/peak):.1f} dBFS  RMS {20*np.log10(rms):.1f} dBFS  时长 {len(pcm)/SR:.2f}s")
