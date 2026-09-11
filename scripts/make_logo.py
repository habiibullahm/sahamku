"""Generate logo Sahamku: assets/logo/{icon.png, icon_dark.png, logo_full.png, icon.svg}.

Usage: python scripts/make_logo.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo"

NAVY = (11, 31, 58)
NAVY_DEEP = (7, 20, 40)
GREEN = (34, 197, 94)
GREEN_DARK = (22, 163, 74)
RED = (239, 68, 68)
WHITE = (255, 255, 255)
GREY = (148, 163, 184)

FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT_SEMI = "C:/Windows/Fonts/seguisb.ttf"

# Candlestick spec (relatif ke kanvas 1000): (x, open, close, low, high, color)
# Tren naik: 1 merah kecil lalu 3 hijau makin tinggi.
CANDLES = [
    (0.26, 0.66, 0.60, 0.70, 0.56, RED),
    (0.40, 0.62, 0.52, 0.66, 0.48, GREEN),
    (0.54, 0.54, 0.42, 0.58, 0.38, GREEN),
    (0.68, 0.44, 0.32, 0.48, 0.28, GREEN),
]
# garis tren (di belakang candle) dari kiri-bawah ke kanan-atas + kepala panah
TREND_FROM, TREND_TO = (0.20, 0.72), (0.82, 0.18)
HEAD_LEN, HEAD_HALF_W = 0.11, 0.06


def arrow_geometry() -> tuple[tuple[float, float], list[tuple[float, float]]]:
    """Return (ujung garis, segitiga kepala) — kepala sejajar arah garis."""
    (fx, fy), (tx, ty) = TREND_FROM, TREND_TO
    dx, dy = tx - fx, ty - fy
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length          # arah
    px, py = -uy, ux                           # tegak lurus
    base = (tx - ux * HEAD_LEN, ty - uy * HEAD_LEN)
    head = [(tx, ty),
            (base[0] + px * HEAD_HALF_W, base[1] + py * HEAD_HALF_W),
            (base[0] - px * HEAD_HALF_W, base[1] - py * HEAD_HALF_W)]
    return base, head


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_mark(img: Image.Image, box: tuple[int, int, int, int], bg: tuple | None,
              radius_pct: float = 0.22) -> None:
    """Gambar ikon di dalam box (x0,y0,x1,y1)."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    s = x1 - x0
    if bg:
        d.rounded_rectangle(box, radius=int(s * radius_pct), fill=bg)

    def P(px: float, py: float) -> tuple[int, int]:
        return (int(x0 + px * s), int(y0 + py * s))

    # garis tren + kepala panah, semi-transparan, di belakang candle
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    lw = int(s * 0.03)
    base, head = arrow_geometry()
    ld.line([P(*TREND_FROM), P(*base)], fill=(255, 255, 255, 210), width=lw)
    r = lw // 2
    fx, fy = P(*TREND_FROM)
    ld.ellipse([fx - r, fy - r, fx + r, fy + r], fill=(255, 255, 255, 210))
    ld.polygon([P(*pt) for pt in head], fill=(255, 255, 255, 210))
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)

    body_w = s * 0.09
    wick_w = max(2, int(s * 0.02))
    for cx, o, c, lo, hi, col in CANDLES:
        x = x0 + cx * s
        d.line([(x, y0 + hi * s), (x, y0 + lo * s)], fill=col, width=wick_w)
        top, bot = y0 + min(o, c) * s, y0 + max(o, c) * s
        d.rounded_rectangle([x - body_w / 2, top, x + body_w / 2, bot],
                            radius=int(body_w * 0.18), fill=col)

    # aksen merah-putih (Indonesia) di bawah
    bar_y = y0 + 0.82 * s
    bar_h = s * 0.045
    d.rounded_rectangle([x0 + 0.18 * s, bar_y, x0 + 0.50 * s, bar_y + bar_h],
                        radius=int(bar_h / 2), fill=RED)
    d.rounded_rectangle([x0 + 0.50 * s, bar_y, x0 + 0.82 * s, bar_y + bar_h],
                        radius=int(bar_h / 2), fill=WHITE)


def make_icon(size: int, bg: tuple, name: str) -> Path:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_mark(img, (0, 0, size, size), bg)
    p = OUT / name
    img.save(p)
    return p


def make_full(w: int = 1800, h: int = 600) -> Path:
    img = Image.new("RGBA", (w, h), NAVY_DEEP)
    d = ImageDraw.Draw(img)
    pad = int(h * 0.15)
    s = h - 2 * pad
    draw_mark(img, (pad, pad, pad + s, pad + s), NAVY)

    tx = pad + s + int(h * 0.12)
    f1 = _font(FONT_BOLD, int(h * 0.36))
    f2 = _font(FONT_SEMI, int(h * 0.11))
    d.text((tx, int(h * 0.20)), "Saham", font=f1, fill=WHITE)
    wsaham = d.textlength("Saham", font=f1)
    d.text((tx + wsaham, int(h * 0.20)), "ku", font=f1, fill=GREEN)
    d.text((tx + 6, int(h * 0.64)), "Daily scan & sinyal AI saham IHSG", font=f2, fill=GREY)
    d.text((tx + 6, int(h * 0.77)), "@sahamku_id_bot", font=f2, fill=GREEN_DARK)
    p = OUT / "logo_full.png"
    img.save(p)
    return p


def make_svg() -> Path:
    s = 1000

    def n(v: float) -> str:
        return f"{v * s:.0f}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}">',
        f'<rect width="{s}" height="{s}" rx="{int(s * 0.22)}" fill="#0B1F3A"/>',
    ]
    for cx, o, c, lo, hi, col in CANDLES:
        hexc = "#EF4444" if col == RED else "#22C55E"
        bw = s * 0.085
        parts.append(f'<line x1="{n(cx)}" y1="{n(hi)}" x2="{n(cx)}" y2="{n(lo)}" '
                     f'stroke="{hexc}" stroke-width="{int(s * 0.018)}" stroke-linecap="round"/>')
        parts.append(f'<rect x="{cx * s - bw / 2:.0f}" y="{n(min(o, c))}" width="{bw:.0f}" '
                     f'height="{abs(o - c) * s:.0f}" rx="{bw * 0.18:.0f}" fill="{hexc}"/>')
    (fx, fy), (base, head) = TREND_FROM, arrow_geometry()
    parts.insert(2, f'<line x1="{n(fx)}" y1="{n(fy)}" x2="{n(base[0])}" y2="{n(base[1])}" '
                    f'stroke="#FFFFFF" stroke-opacity="0.82" stroke-width="{int(s * 0.03)}" '
                    f'stroke-linecap="round"/>')
    pts = " ".join(f"{n(x)},{n(y)}" for x, y in head)
    parts.insert(3, f'<polygon points="{pts}" fill="#FFFFFF" fill-opacity="0.82"/>')
    by, bh = 0.82, 0.045
    parts.append(f'<rect x="{n(0.18)}" y="{n(by)}" width="{n(0.32)}" height="{n(bh)}" '
                 f'rx="{n(bh / 2)}" fill="#EF4444"/>')
    parts.append(f'<rect x="{n(0.50)}" y="{n(by)}" width="{n(0.32)}" height="{n(bh)}" '
                 f'rx="{n(bh / 2)}" fill="#FFFFFF"/>')
    parts.append("</svg>")
    p = OUT / "icon.svg"
    p.write_text("\n".join(parts), encoding="utf-8")
    return p


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (make_icon(1024, NAVY, "icon.png"),
              make_icon(1024, NAVY_DEEP, "icon_dark.png"),
              make_icon(512, NAVY, "icon_512.png"),
              make_full(), make_svg()):
        print(p)
