"""Analisis pre-market: sentimen global + posisi teknikal IHSG + watchlist."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from sahamku import db
from sahamku.indicators.technical import compute
from sahamku.universe import GLOBAL_TICKERS, IHSG, from_yf, to_yf


@dataclass
class PreMarketReport:
    date: str
    sentiment_score: int
    sentiment_label: str
    global_rows: list[tuple[str, float | None, float | None]]  # (nama, close, pct)
    ihsg_close: float | None
    ihsg_pct: float | None
    ihsg_rsi: float | None
    ihsg_trend: str
    support: float | None
    resistance: float | None
    notes: list[str] = field(default_factory=list)
    bullish_yesterday: list[str] = field(default_factory=list)
    bearish_yesterday: list[str] = field(default_factory=list)
    watchlist: dict[str, str] = field(default_factory=dict)


# Kontribusi ke sentimen IHSG: +1 jika naik searah, -1 jika berlawanan (USD/IDR & yield inverse)
SENTIMENT_WEIGHT = {
    "^GSPC": 1, "^IXIC": 1, "^DJI": 1, "ES=F": 2,
    "^N225": 1, "^HSI": 1, "^KS11": 1,
    "CL=F": 0, "GC=F": 0,
    "IDR=X": -1, "^TNX": -1,
}
MOVE_THRESHOLD = 0.3  # % — di bawah ini dianggap flat


def build(conn: sqlite3.Connection, for_date: date | None = None,
          watch_codes: list[str] | None = None) -> PreMarketReport | None:
    for_date = for_date or date.today()
    ihsg_df = db.load_ohlcv(conn, IHSG)
    if ihsg_df.empty:
        return None
    joined = ihsg_df.join(compute(ihsg_df))
    last = joined.iloc[-1]
    prev = joined.iloc[-2] if len(joined) > 1 else last
    ihsg_pct = (last["close"] / prev["close"] - 1) * 100 if prev["close"] else None
    yday = joined.index[-1].strftime("%Y-%m-%d")

    # Global rows + skor
    rows: list[tuple[str, float | None, float | None]] = []
    score = 0
    notes: list[str] = []
    for t, name in GLOBAL_TICKERS.items():
        g = db.load_ohlcv(conn, t, limit=2, table="global_ohlcv")
        if len(g) < 2:
            rows.append((name, None, None))
            continue
        c1, c0 = float(g["close"].iloc[-1]), float(g["close"].iloc[-2])
        p = (c1 / c0 - 1) * 100 if c0 else None
        rows.append((name, c1, p))
        w = SENTIMENT_WEIGHT.get(t, 0)
        if p is not None and abs(p) >= MOVE_THRESHOLD and w:
            score += w * (1 if p > 0 else -1)
        if t == "CL=F" and p is not None and abs(p) >= 2:
            notes.append(f"Minyak {'naik' if p > 0 else 'turun'} {abs(p):.1f}% → "
                         "perhatikan sektor energi (MEDC, PGAS, AKRA)")
        if t == "GC=F" and p is not None and abs(p) >= 1.5:
            notes.append(f"Emas {'naik' if p > 0 else 'turun'} {abs(p):.1f}% → "
                         "perhatikan ANTM, MDKA")
        if t == "IDR=X" and p is not None and p >= 0.5:
            notes.append(f"Rupiah melemah {p:.2f}% → tekanan pada saham berbasis impor/USD debt")

    label = "BULLISH" if score >= 3 else "BEARISH" if score <= -3 else "NETRAL"

    # Level IHSG: support/resistance dari swing 20 hari + trend vs SMA
    support = float(joined["low"].tail(20).min())
    resistance = float(joined["high"].tail(20).max())
    trend = trend_label(last)

    # Sinyal dari scan kemarin
    bull, bear = [], []
    for r in db.ratings_on(conn, yday):
        if r["rating"] == "bullish":
            bull.append(from_yf(r["ticker"]))
        elif r["rating"] == "bearish":
            bear.append(from_yf(r["ticker"]))

    watch: dict[str, str] = {}
    for code in watch_codes or []:
        watch[code] = _watch_info(conn, code, yday)

    return PreMarketReport(
        date=for_date.isoformat(),
        sentiment_score=score, sentiment_label=label, global_rows=rows,
        ihsg_close=float(last["close"]), ihsg_pct=ihsg_pct,
        ihsg_rsi=None if pd.isna(last["rsi14"]) else float(last["rsi14"]),
        ihsg_trend=trend, support=support, resistance=resistance,
        notes=notes, bullish_yesterday=bull[:10], bearish_yesterday=bear[:10], watchlist=watch,
    )


def trend_label(row: pd.Series) -> str:
    c, s20, s50, s200 = row["close"], row["sma20"], row["sma50"], row["sma200"]
    if pd.isna(s200):
        return "data SMA200 belum cukup"
    if c > s20 > s50 > s200:
        return "uptrend kuat (di atas semua SMA)"
    if c > s200:
        return "di atas SMA200, tren jangka panjang naik"
    if c < s20 < s50 < s200:
        return "downtrend kuat (di bawah semua SMA)"
    return "di bawah SMA200, tren jangka panjang turun"


def _watch_info(conn: sqlite3.Connection, code: str, yday: str) -> str:
    t = to_yf(code)
    df = db.load_ohlcv(conn, t)
    if df.empty:
        return "data tidak ada"
    j = df.join(compute(df))
    last = j.iloc[-1]
    close = float(last["close"])
    sup = float(j["low"].tail(20).min())
    res = float(j["high"].tail(20).max())
    parts = [f"close {close:,.0f}"]
    if res and (res - close) / close <= 0.02:
        parts.append(f"dekat resistance {res:,.0f}")
    if sup and (close - sup) / close <= 0.02:
        parts.append(f"dekat support {sup:,.0f}")
    r = db.rating_for(conn, t, yday)
    if r:
        parts.append(f"{r['rating']} ({r['score']:+d})")
    return " · ".join(parts)
