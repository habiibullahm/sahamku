"""Logo bot Hermes pribadi (avatar Telegram): huruf H bersayap, latar gelap.

Usage: python scripts/make_logo_hermes.py
Output: assets/logo/hermes_icon.png (1024) & hermes_icon_512.png
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "logo"
BG = (24, 22, 40)          # ungu-gelap
BG_RING = (58, 52, 96)
GOLD = (245, 197, 66)
GOLD_DARK = (214, 160, 40)
TEAL = (56, 214, 190)
WHITE = (248, 246, 255)
FONT = "C:/Windows/Fonts/segoeuib.ttf"


def wing(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, direction: int) -> None:
    """Sayap 3 bulu (bezier sederhana via polygon) ke kiri (-1) atau kanan (+1)."""
    for i, (length, lift, w) in enumerate(((0.30, 0.10, 0.075), (0.25, 0.02, 0.065),
                                           (0.20, -0.06, 0.055))):
        x0, y0 = cx, cy + i * s * 0.07
        x1 = cx + direction * length * s
        y1 = y0 - lift * s
        pts = []
        for t in (k / 24 for k in range(25)):
            # kurva ke atas lalu meruncing
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t - math.sin(t * math.pi) * s * 0.06
            pts.append((x, y))
        back = []
        for t in (k / 24 for k in range(24, -1, -1)):
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t + (1 - t) * w * s
            back.append((x, y))
        d.polygon(pts + back, fill=GOLD if i % 2 == 0 else GOLD_DARK)


def make(size: int) -> Path:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.rounded_rectangle((0, 0, s, s), radius=int(s * 0.22), fill=BG)
    # cincin tipis
    d.ellipse((s * 0.11, s * 0.11, s * 0.89, s * 0.89), outline=BG_RING,
              width=max(2, int(s * 0.012)))

    # sayap kiri & kanan, sedikit di atas tengah
    wing(d, s * 0.41, s * 0.44, s, -1)
    wing(d, s * 0.59, s * 0.44, s, +1)

    # huruf H
    f = ImageFont.truetype(FONT, int(s * 0.46))
    tw = d.textlength("H", font=f)
    d.text(((s - tw) / 2, s * 0.25), "H", font=f, fill=WHITE)

    # titik teal kecil = "agent aktif"
    r = s * 0.035
    d.ellipse((s * 0.5 - r, s * 0.79 - r, s * 0.5 + r, s * 0.79 + r), fill=TEAL)

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"hermes_icon{'' if size == 1024 else '_' + str(size)}.png"
    img.save(p)
    return p


if __name__ == "__main__":
    for sz in (1024, 512):
        print(make(sz))
