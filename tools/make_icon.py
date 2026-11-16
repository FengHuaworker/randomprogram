# -*- coding: utf-8 -*-
"""开发脚本：生成莫兰迪风格应用图标 app_icon.ico（多尺寸）。"""

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\msyhbd.ttc"
OUT = "assets/app_icon.ico"


def draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角矩形底（雾霾蓝渐变：上浅下深）
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(139 + (117 - 139) * t)
        g = int(168 + (147 - 168) * t)
        b = int(199 + (180 - 199) * t)
        gd.line([(0, y), (size, y)], fill=(r, g, b, 255), width=1)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.22, fill=255)
    img.paste(grad, (0, 0), mask)
    # 中心“抽”字（白色）
    fsize = int(size * 0.55)
    try:
        font = ImageFont.truetype(FONT, fsize)
    except Exception:
        font = ImageFont.load_default()
    txt = "抽"
    bbox = d.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), txt,
           font=font, fill=(255, 255, 255, 255))
    return img


def main():
    import os
    os.makedirs("assets", exist_ok=True)
    base = draw(256)
    base.save(OUT, format="ICO",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon saved:", OUT)


if __name__ == "__main__":
    main()
