"""Analisis after-market: ringkasan IHSG, top movers, sinyal, watchlist."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from sahamku import db, levels
from sahamku.analysis import growth
from sahamku.config import settings
from sahamku.indicators.technical import compute
from sahamku.signals.rules import RULE_LABELS, STATE_RULES
from sahamku.universe import IHSG, from_yf, scan_tickers, universe_label


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
    universe: str = "universe aktif"
    eligible_count: int = 0
    coverage_pct: float = 0.0
    data_complete: bool = True
    ihsg_rsi: float | None = None
    ihsg_trend: str = ""
    support: float | None = None
    resistance: float | None = None
    liquid_momentum: list[growth.GrowthCandidate] = field(default_factory=list)
    growth_candidates: list[growth.GrowthCandidate] = field(default_factory=list)
    watch_tomorrow: list[str] = field(default_factory=list)


def build(conn: sqlite3.Connection, date_str: str | None = None,
          watch_codes: list[str] | None = None, missing: list[str] | None = None,
          top_n: int = 5) -> AfterMarketReport | None:
    date_str = date_str or db.latest_date(conn, ticker=IHSG)
    if not date_str:
        return None
    snap = db.close_on(conn, date_str)
    if snap.empty:
        return None
    snap["pct"] = (snap["close"] / snap["prev_close"] - 1) * 100

    if settings.universe.lower() == "liquid" and not conn.execute(
        "SELECT 1 FROM universe_eligibility WHERE date=? LIMIT 1", (date_str,)
    ).fetchone():
        growth.compute_and_store(conn, date_str)

    ihsg = snap.loc[IHSG] if IHSG in snap.index else None
    selected = scan_tickers(conn, date_str)
    stocks = snap.loc[[t for t in selected if t in snap.index]].dropna(subset=["pct"])
    movers = [Mover(from_yf(t), r["close"], r["pct"], r["volume"]) for t, r in stocks.iterrows()]
    movers.sort(key=lambda m: m.pct, reverse=True)

    by_code = _signals_by_code(conn, date_str, set(selected))
    bullish = sorted([s for s in by_code.values() if s.rating == "bullish"],
                     key=lambda s: -s.score)
    bearish = sorted([s for s in by_code.values() if s.rating == "bearish"],
                     key=lambda s: s.score)
    squeeze = [c for c, s in by_code.items() if any("squeeze" in r for r in s.rules)]

    mover_by_code = {m.code: m for m in movers}
    watch = {c: (mover_by_code.get(c), by_code.get(c)) for c in (watch_codes or [])}

    _, all_growth = growth.latest(conn, limit=1000, min_score=0, date_str=date_str)
    liquid_momentum = sorted(
        [g for g in all_growth if g.rel_60 is not None], key=lambda g: g.rel_60 or -999,
        reverse=True,
    )[:5]
    growth_candidates = [g for g in all_growth
                         if g.total >= settings.potential_growth_min_score][:5]
    _, expected, cov = growth.coverage(conn, date_str)
    ihsg_df = db.load_ohlcv(conn, IHSG)
    joined = ihsg_df.join(compute(ihsg_df)) if not ihsg_df.empty else ihsg_df
    last = joined.iloc[-1] if len(joined) else None
    lv = levels.compute(ihsg_df) if not ihsg_df.empty else None
    support = lv.supports[0] if lv and lv.supports else None
    resistance = lv.resistances[0] if lv and lv.resistances else None
    from sahamku.analysis.premarket import trend_label
    trend = trend_label(last) if last is not None else ""
    watch_next = _watch_next(float(ihsg["close"]) if ihsg is not None else None,
                             support, resistance, len(stocks),
                             int((stocks["pct"] > 0).sum()), growth_candidates)

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
        watchlist=watch, universe=universe_label(conn), eligible_count=len(selected),
        coverage_pct=cov * 100 if expected else 100.0,
        data_complete=(not expected or cov >= settings.universe_min_coverage),
        ihsg_rsi=_f(last, "rsi14"), ihsg_trend=trend, support=support,
        resistance=resistance, liquid_momentum=liquid_momentum,
        growth_candidates=growth_candidates, watch_tomorrow=watch_next,
    )


def _signals_by_code(conn: sqlite3.Connection, date_str: str,
                     allowed: set[str] | None = None) -> dict[str, TickerSignals]:
    out: dict[str, TickerSignals] = {}
    for r in db.ratings_on(conn, date_str):
        if allowed is None or r["ticker"] in allowed:
            out[from_yf(r["ticker"])] = TickerSignals(
                from_yf(r["ticker"]), r["score"], r["rating"])
    for r in db.signals_on(conn, date_str):
        if r["rule"] in STATE_RULES:
            continue
        code = from_yf(r["ticker"])
        if code not in out:
            continue
        label = RULE_LABELS.get(r["rule"], r["rule"])
        out[code].rules.append(f"{label} ({r['detail']})" if r["detail"] else label)
    return out


def _watch_next(close: float | None, support: float | None, resistance: float | None,
                total: int, advancers: int,
                candidates: list[growth.GrowthCandidate]) -> list[str]:
    out = []
    if support:
        out.append(f"IHSG bertahan di atas support {support:,.0f}")
    if resistance:
        out.append(f"IHSG menembus resistance {resistance:,.0f} dengan breadth membaik")
    if total:
        out.append(f"breadth membaik di atas {total // 2} saham naik")
    if candidates:
        out.append("pemimpin Potential Growth menguat dengan volume terkonfirmasi")
    return out[:4]


def _f(row: pd.Series | None, col: str) -> float | None:
    if row is None:
        return None
    v = row[col]
    return None if pd.isna(v) else float(v)
