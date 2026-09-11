"""Support/resistance otomatis dari swing high/low (pivot) dengan pengelompokan level."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Levels:
    supports: list[float]      # terdekat dulu (di bawah harga)
    resistances: list[float]   # terdekat dulu (di atas harga)
    close: float


def _pivots(s: pd.Series, window: int, high: bool) -> list[float]:
    """Nilai pivot: titik yang tertinggi/terendah dalam ±window bar."""
    out: list[float] = []
    vals = s.to_numpy()
    n = len(vals)
    for i in range(window, n - window):
        seg = vals[i - window:i + window + 1]
        if (high and vals[i] == seg.max()) or (not high and vals[i] == seg.min()):
            out.append(float(vals[i]))
    return out


def _cluster(levels: list[float], tol: float) -> list[float]:
    """Gabungkan level yang berjarak < tol (relatif); ambil rata-rata tiap kelompok."""
    if not levels:
        return []
    levels = sorted(levels)
    groups: list[list[float]] = [[levels[0]]]
    for v in levels[1:]:
        if abs(v - groups[-1][-1]) / groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    # kelompok dengan lebih banyak sentuhan lebih kuat, tetapi urutan akhir tetap by harga
    return [sum(g) / len(g) for g in groups]


def compute(df: pd.DataFrame, lookback: int = 120, window: int = 5, tol: float = 0.015,
            max_each: int = 2) -> Levels:
    """df: OHLC (index tanggal). Return level S/R terdekat dari close terakhir."""
    d = df.tail(lookback)
    close = float(d["close"].iloc[-1])
    # pivot tak terbentuk di `window` bar terakhir → tambahkan ekstrem terbaru sebagai kandidat
    recent = d.tail(2 * window)
    highs = _cluster(_pivots(d["high"], window, True) + [float(recent["high"].max())], tol)
    lows = _cluster(_pivots(d["low"], window, False) + [float(recent["low"].min())], tol)
    # level bisa berasal dari high maupun low; yang di bawah close = support, di atas = resistance
    all_levels = sorted(set(highs + lows))
    supports = [v for v in all_levels if v < close * (1 - 0.002)]
    resistances = [v for v in all_levels if v > close * (1 + 0.002)]
    supports = sorted(supports, key=lambda v: close - v)[:max_each]
    resistances = sorted(resistances, key=lambda v: v - close)[:max_each]
    return Levels(supports, resistances, close)


def describe(lv: Levels) -> str:
    s = " · ".join(f"S{i + 1} {v:,.0f}" for i, v in enumerate(lv.supports)) or "S —"
    r = " · ".join(f"R{i + 1} {v:,.0f}" for i, v in enumerate(lv.resistances)) or "R —"
    return f"{s} | {r}"
