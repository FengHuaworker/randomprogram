# -*- coding: utf-8 -*-
"""采样截图像素，定位淡色按钮命中的颜色。"""
from PIL import Image

img = Image.open(r'E:\DeepseekHarness\qq-bridge\state\agents\random-picker\ui_preview\probe_wiz3_fixed.png').convert('RGB')
w, h = img.size
print('size', w, h)

def sample(x, y, label):
    print(label, img.getpixel((x, y)))

# 弹窗卡片中心坐标（1284x804 截图中卡片约占 434~850 宽）
# btn_pick 按钮行位于卡片中部（y≈352 截图坐标=实际x2? 先探测列扫描）
# 直接扫描整行 y=352（截图中灰色卡内），打印该行差异颜色
for y in (330, 352, 375):
    row = [img.getpixel((x, y)) for x in range(430, 860, 6)]
    uniq = sorted(set(row))
    print('y=%d uniq colors:' % y, uniq[:6])
