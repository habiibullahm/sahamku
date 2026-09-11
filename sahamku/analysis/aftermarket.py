"""Analisis after-market: ringkasan IHSG, top movers, sinyal, watchlist."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from sahamku import db
from sahamku.signals.rules import RULE_LABELS, STATE_RULES
from sahamku.universe import IHSG, STOCK_TICKERS, from_yf


@dataclass
class Mover:
    code: str
    close: float
    pct: float
    volume: float


@dataclass
class TickerSignals:
    code: str
    score: int
    rating: str
    rules: list[str] = field(default_factory=list)  # label + detail


@dataclass
class AfterMarketReport:
    date: str
    ihsg_close: float | None
    ihsg_pct: float | None
    ihsg_volume: float | None
    advancers: int
    decliners: int
    unchanged: int
    gainers: list[Mover]
    losers: list[Mover]
    bullish: list[TickerSignals]
    bearish: list[TickerSignals]
    squeeze: list[str]
    missing: list[str]
    watchlist: dict[str, tuple[Mover | None, TickerSignals | None]] = field(default_factory=dict)


def build(conn: sqlite3.Connection, date_str: str | None = None,
          watch_codes: list[str] | None = None, missing: list[str] | None = None,
          top_n: int = 5) -> AfterMarketReport | None:
    date_str = date_str or db.latest_date(conn)
    if not date_str:
        return None
    snap = db.close_on(conn, date_str)
    if snap.empty:
        return None
    snap["pct"] = (snap["close"] / snap["prev_close"] - 1) * 100

    ihsg = snap.loc[IHSG] if IHSG in snap.index else None
    stocks = snap.loc[[t for t in STOCK_TICKERS if t in snap.index]].dropna(subset=["pct"])
    movers = [Mover(from_yf(t), r["close"], r["pct"], r["volume"]) for t, r in stocks.iterrows()]
    movers.sort(key=lambda m: m.pct, reverse=True)

    by_code = _signals_by_code(conn, date_str)
    bullish = sorted([s for s in by_code.values() if s.rating == "bullish"],
                     key=lambda s: -s.score)
    bearish = sorted([s for s in by_code.values() if s.rating == "bearish"],
                     key=lambda s: s.score)
    squeeze = [c for c, s in by_code.items() if any("squeeze" in r for r in s.rules)]

    mover_by_code = {m.code: m for m in movers}
    watch = {c: (mover_by_code.get(c), by_code.get(c)) for c in (watch_codes or [])}

    return AfterMarketReport(
        date=date_str,
        ihsg_close=_f(ihsg, "close"), ihsg_pct=_f(ihsg, "pct"), ihsg_volume=_f(ihsg, "volume"),
        advancers=int((stocks["pct"] > 0).sum()),
        decliners=int((stocks["pct"] < 0).sum()),
        unchanged=int((stocks["pct"] == 0).sum()),
        gainers=movers[:top_n],
        losers=list(reversed(movers[-top_n:])),
        bullish=bullish, bearish=bearish, squeeze=squeeze,
        missing=[from_yf(m) for m in (missing or [])],
        watchlist=watch,
    )


def _signals_by_code(conn: sqlite3.Connection, date_str: str) -> dict[str, TickerSignals]:
    out: dict[str, TickerSignals] = {}
    for r in db.ratings_on(conn, date_str):
        out[from_yf(r["ticker"])] = TickerSignals(from_yf(r["ticker"]), r["score"], r["rating"])
    for r in db.signals_on(conn, date_str):
        if r["rule"] in STATE_RULES:
            continue
        code = from_yf(r["ticker"])
        label = RULE_LABELS.get(r["rule"], r["rule"])
        out[code].rules.append(f"{label} ({r['detail']})" if r["detail"] else label)
    return out


def _f(row: pd.Series | None, col: str) -> float | None:
    if row is None:
        return None
    v = row[col]
    return None if pd.isna(v) else float(v)
