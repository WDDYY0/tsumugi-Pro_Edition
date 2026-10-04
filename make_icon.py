# -*- coding: utf-8 -*-
"""生成 tsumugi.ico 图标文件（输出到 resources 文件夹）"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
RES_DIR = ROOT / "resources"
RES_DIR.mkdir(exist_ok=True)
OUT = RES_DIR / "tsumugi.ico"


def make_base(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = int(size * 0.06)
    radius = int(size * 0.22)

    for y in range(pad, size - pad):
        t = (y - pad) / max(1, (size - 2 * pad))
        r = int(58 + (140 - 58) * t)
        g = int(90 + (70 - 90) * t)
        b = int(200 + (180 - 200) * t)
        d.line([(pad, y), (size - pad, y)], fill=(r, g, b, 255))

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([pad, pad, size - pad, size - pad],
                         radius=radius, fill=255)
    img.putalpha(mask)

    cx, cy = size // 2, size // 2
    stem_x = int(cx + size * 0.10)
    stem_top = int(cy - size * 0.28)
    stem_bottom = int(cy + size * 0.18)
    stem_w = max(2, int(size * 0.045))
    d.rectangle([stem_x - stem_w // 2, stem_top, stem_x + stem_w // 2, stem_bottom],
                fill=(255, 255, 255, 255))

    head_r = int(size * 0.10)
    head_cx = int(stem_x - size * 0.10)
    head_cy = stem_bottom
    d.ellipse([head_cx - head_r, head_cy - head_r * 0.75,
               head_cx + head_r, head_cy + head_r * 0.75],
              fill=(255, 255, 255, 255))

    d.line([(stem_x, stem_top),
            (stem_x + int(size * 0.13), stem_top + int(size * 0.06))],
           fill=(255, 255, 255, 255), width=max(2, int(size * 0.035)))

    wave_y = int(size - pad - size * 0.14)
    bar_h = max(2, int(size * 0.025))
    for i, h_ratio in enumerate([0.35, 0.55, 0.75, 0.5, 0.3]):
        x = int(pad + size * 0.10 + i * size * 0.16)
        h = int(size * 0.14 * h_ratio)
        d.rectangle([x, wave_y - h // 2, x + bar_h, wave_y + h // 2],
                    fill=(255, 255, 255, 220))

    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_base(s) for s in sizes]
    images[0].save(str(OUT), format="ICO",
                   sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    print(f"图标已生成：{OUT}")
    print(f"包含尺寸：{sizes}")


if __name__ == "__main__":
    main()