# -*- coding: utf-8 -*-
"""科目配色：给每个科目分配"彼此差异明显、且不与空节浅灰混淆"的颜色。

算法（没有现成库里合适的，所以自己写）：
1. 候选色铺在 Oklab 感知均匀空间里（亮度 4 档 × 色相每 4° 一圈 × 彩度 4 档），
   丢掉超出 sRGB 色域的、以及在白卡片上看不见的淡色，得到约 1000 个候选；
2. 用"最远点采样"依次选色：每加一门课，就挑离"已选颜色 + 保留色"最远的候选色。
   保留色 = 空节横杠的浅灰、次级灰字、主文字、白，所以不会撞色；
   第一步从接近 #3B82F6 的候选色起步（好看，且离灰/白都远）；
3. 色盲（红色盲/绿色盲）距离只作为"同分时的优先级"，不牺牲正常视觉的区分度；
4. 颜色分配后写进 subjects.json：以后新增科目只会追加新颜色，不会打乱已有颜色。

颜色呈现（display.py 用）：
- 描边 border() = 原色满强度，最醒目，是"一眼分清科目"的主要线索；
- 文字 ink()    = 原色，若在淡底上对比度不足 4.5:1 就压暗到够（保持色相）；
- 淡底 tint()   = 原色与白色按 TINT_W 混合（只做氛围，不承担区分度）。
"""
import colorsys
import math

TINT_W = 0.86            # 淡底 = 14% 科目色 + 86% 白
DEFAULT_COLOR = "#3B82F6"
EMPTY_COLOR = "#7C8595"  # 空节横杠的灰（"没课"标识；配色算法会主动避开这个灰）

# 保留色：空节横杠、次级灰字、主文字、白（彩度极低，用来"避开"）
RESERVED = (EMPTY_COLOR, "#6B7280", "#111827", "#FFFFFF")
SEED_TARGET = "#3B82F6"

L_LEVELS = (0.45, 0.53, 0.61, 0.69)
C_LEVELS = (0.06, 0.10, 0.14, 0.18)
HUE_STEP = 4
MIN_BORDER_CONTRAST = 2.5      # 描边在白卡片上的最低对比度

# Machado 2009 色盲模拟矩阵（severity 1.0，作用于线性 RGB）
_CVD_MATRICES = (
    ((0.152286, 1.052583, -0.204868),
     (0.114503, 0.786281, 0.099216),
     (-0.003882, -0.048116, 1.051998)),
    ((0.367322, 0.860646, -0.227968),
     (0.280085, 0.672501, 0.047413),
     (-0.011820, 0.042940, 0.968881)),
)


# ---------------------------------------------------------------- 颜色空间

def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def is_valid_color(text):
    """'#RRGGBB' / 'RRGGBB' 是否合法。"""
    if not isinstance(text, str):
        return False
    t = text.strip().lstrip("#")
    if len(t) != 6:
        return False
    try:
        int(t, 16)
    except ValueError:
        return False
    return True


def normalize_color(text):
    return "#" + text.strip().lstrip("#").upper()


def hex_to_rgb(hex_color):
    h = normalize_color(hex_color).lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def rgb_to_hex(rgb):
    return "#" + "".join("%02X" % int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb)


def srgb_to_oklab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1.0 / 3.0)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1.0 / 3.0)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1.0 / 3.0)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_srgb(lab):
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (_gam(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
            _gam(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            _gam(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s))


def _dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _luminance(hex_color):
    r, g, b = (_lin(c) for c in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a, hex_b):
    """WCAG 对比度（1~21）。"""
    la, lb = _luminance(hex_a), _luminance(hex_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(hex_a, hex_b, w):
    """sRGB 线性插值：w=0 全 a，w=1 全 b。"""
    ra, ga, ba = hex_to_rgb(hex_a)
    rb, gb, bb = hex_to_rgb(hex_b)
    return rgb_to_hex((ra + (rb - ra) * w, ga + (gb - ga) * w, ba + (bb - ba) * w))


def tint(color):
    """淡底（只做氛围）。"""
    return mix(color, "#FFFFFF", TINT_W)


def border(color):
    """描边：原色满强度，负责"一眼分清"。"""
    return normalize_color(color)


def ink(color, min_contrast=4.5):
    """文字色：优先原色，对比度不够才逐步压暗（保持色相）。"""
    base = normalize_color(color)
    t = tint(base)
    if contrast_ratio(base, t) >= min_contrast:
        return base
    for step in range(2, 61, 2):
        cand = mix(base, "#000000", step / 100.0)
        if contrast_ratio(cand, t) >= min_contrast:
            return cand
    return mix(base, "#000000", 0.6)


def _apply_cvd(hex_color, matrix):
    r, g, b = (_lin(c) for c in hex_to_rgb(hex_color))
    out = [_gam(row[0] * r + row[1] * g + row[2] * b) for row in matrix]
    return rgb_to_hex(out)


def _cvd_labs(hex_color):
    return tuple(srgb_to_oklab(hex_to_rgb(_apply_cvd(hex_color, m))) for m in _CVD_MATRICES)


# ---------------------------------------------------------------- 候选色池

_POOL = None


def _pool():
    """候选色池：每项 = (hex, oklab, (红色盲 oklab, 绿色盲 oklab))。"""
    global _POOL
    if _POOL is not None:
        return _POOL
    pool = []
    for L in L_LEVELS:
        for hue in range(0, 360, HUE_STEP):
            rad = math.radians(hue)
            for C in C_LEVELS:
                lab = (L, C * math.cos(rad), C * math.sin(rad))
                rgb = oklab_to_srgb(lab)
                if not all(-0.004 <= c <= 1.004 for c in rgb):
                    continue
                hex_color = rgb_to_hex(rgb)
                if hex_color in RESERVED:
                    continue
                if contrast_ratio(hex_color, "#FFFFFF") < MIN_BORDER_CONTRAST:
                    continue
                pool.append((hex_color, srgb_to_oklab(hex_to_rgb(hex_color)), _cvd_labs(hex_color)))
    _POOL = pool
    return pool


def pick_palette(count, used=()):
    """取 count 个彼此差异明显的颜色；used 是已经占用的颜色（不会再选到）。"""
    pool = _pool()
    used = [normalize_color(c) for c in used if is_valid_color(c)]
    chosen = [(c, srgb_to_oklab(hex_to_rgb(c)), _cvd_labs(c)) for c in used + list(RESERVED)]
    picked = []
    if not used:
        target = srgb_to_oklab(hex_to_rgb(SEED_TARGET))
        seed = min(pool, key=lambda item: _dist(item[1], target))
        picked.append(seed[0])
        chosen.append(seed)
    while len(picked) < count:
        best, best_score = None, -1.0
        for item in pool:
            d = min(_dist(item[1], other[1]) for other in chosen)
            cd = min(min(_dist(item[2][i], other[2][i]) for i in range(len(_CVD_MATRICES)))
                     for other in chosen)
            score = d + 0.001 * cd          # 正常视觉距离为主，色盲距离做同分优先级
            if score > best_score:
                best, best_score = item, score
        picked.append(best[0])
        chosen.append(best)
    return picked


def ensure_colors(subjects):
    """给缺颜色的科目补色（直接改 subjects 里的 dict），返回是否有改动。"""
    if not subjects:
        return False
    used = [s["color"] for s in subjects if is_valid_color(s.get("color"))]
    missing = [s for s in subjects if not is_valid_color(s.get("color"))]
    if not missing:
        return False
    for sub, col in zip(missing, pick_palette(len(missing), used)):
        sub["color"] = col
    return True


def color_of(subject):
    """取科目颜色（缺失时给默认蓝）。"""
    c = (subject or {}).get("color")
    return normalize_color(c) if is_valid_color(c) else DEFAULT_COLOR


def chip_style(color):
    """给 QSS 用的三件套：淡底 / 描边 / 文字。"""
    base = normalize_color(color) if is_valid_color(color) else DEFAULT_COLOR
    return {"bg": tint(base), "border": border(base), "text": ink(base)}


def hsv(color):
    """调试用：返回 (色相, 饱和度, 明度)。"""
    return colorsys.rgb_to_hsv(*hex_to_rgb(color))
