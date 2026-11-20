# -*- coding: utf-8 -*-
"""UniSchedule 图标生成：蓝白清爽 + 课表横条方案。

输出：icon.ico（16/24/32/48/64/128/256 多尺寸）+ icon_preview.png（预览）。
想调样式改下方常量后重跑即可。
"""
from PIL import Image, ImageDraw

S = 256                      # 基准尺寸
RADIUS = 58                  # 背景圆角半径
TOP = (94, 168, 232)         # 渐变顶 浅蓝
BOTTOM = (24, 95, 165)       # 渐变底 深蓝
BAR = (255, 255, 255, 255)   # 白色横条
GRIDS = [(230, 241, 251), (133, 183, 235), (55, 138, 221), (24, 95, 165)]  # 格子 浅→深
GRID_GAP = 12                # 格子间距
GRID_W = 34                  # 格子宽
GRID_H = 36                  # 格子高


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main():
    # 圆角渐变背景
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for y in range(S):
        color = lerp(TOP, BOTTOM, y / S)
        ImageDraw.Draw(bg).line([(0, y), (S, y)], fill=color + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=RADIUS, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # 白色圆角横条（居中偏上，加宽让 4 格完整可见）
    bar_x0, bar_y0, bar_x1, bar_y1 = 28, 96, 228, 156
    d.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=30, fill=BAR)

    # 条内 4 个蓝色格子（浅→深，最右高亮）
    n = len(GRIDS)
    total_w = n * GRID_W + (n - 1) * GRID_GAP
    start_x = (bar_x0 + bar_x1 - total_w) // 2
    cy = (bar_y0 + bar_y1) // 2
    for i, c in enumerate(GRIDS):
        x0 = start_x + i * (GRID_W + GRID_GAP)
        y0 = cy - GRID_H // 2
        d.rounded_rectangle([x0, y0, x0 + GRID_W, y0 + GRID_H], radius=9, fill=c + (255,))

    img.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                (64, 64), (128, 128), (256, 256)])
    img.save("icon_preview.png")
    print("[OK] icon.ico (multi-size) + icon_preview.png generated")


if __name__ == "__main__":
    main()
