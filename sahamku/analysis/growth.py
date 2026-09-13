"""Liquid-universe eligibility and transparent Potential Growth ranking."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sahamku import db
from sahamku.config import settings
from sahamku.universe import IHSG, active_tickers, from_yf


@dataclass(frozen=True)
class GrowthCandidate:
    code: str
    total: float
    liquidity: float
    momentum: float
    trend: float
    breakout: float
    accumulation_risk: float
    rel_60: float | None
    median_value_20: float | None
    explanations: list[str]
    risk_flags: list[str]


def compute_and_store(conn: sqlite3.Connection, date_str: str | None = None) -> int:
    date_str = date_str or db.latest_date(conn, ticker=IHSG)
    if not date_str:
        return 0
    candidates = active_tickers(conn)
    raw: list[dict] = []
    eligibility: list[tuple] = []
    ihsg = db.load_ohlcv(conn, IHSG)
    ihsg = ihsg.loc[:date_str]

    for ticker in candidates:
        frame = db.load_ohlcv(conn, ticker).loc[:date_str]
        stats = _liquidity_stats(frame, ihsg)
        item, reason = _raw_metrics(frame, ihsg, date_str, stats)
        n = len(frame)
        traded20, traded60 = stats["traded20"], stats["traded60"]
        med20, med60 = stats["med20"], stats["med60"]
        eligibility.append((ticker, 0 if reason else 1, n, traded20, traded60,
                            med20, med60, reason))
        if item is not None:
            item.update(ticker=ticker, med20=med20, med60=med60,
                        coverage=(traded20 / 20 + traded60 / 60) / 2)
            raw.append(item)

    db.replace_eligibility(conn, date_str, eligibility)
    if not raw:
        db.replace_growth_scores(conn, date_str, [])
        conn.commit()
        return 0

    df = pd.DataFrame(raw)
    liquidity_rank = (
        df["med20"].map(math.log).rank(pct=True) * 0.45
        + df["med60"].map(math.log).rank(pct=True) * 0.35
        + df["coverage"] * 0.20
    )
    momentum_rank = sum(
        df[col].clip(df[col].quantile(.05), df[col].quantile(.95)).rank(pct=True) * weight
        for col, weight in (("rel20", .30), ("rel60", .40), ("rel120", .30))
    )
    vol_quality = 1 - df["volatility"].rank(pct=True)
    drawdown_quality = 1 - df["drawdown"].rank(pct=True)

    rows: list[tuple] = []
    for i, item in df.iterrows():
        liq = float(liquidity_rank.loc[i] * 20)
        mom = float(momentum_rank.loc[i] * 25)
        trend = _trend_score(item)
        breakout = _breakout_score(item)
        accum = min(5.0, max(0.0, float(item.up_volume_share) * 5))
        if item.ret20 > 0:
            accum += min(5.0, max(0.0, float(item.volume_ratio_5_20) / 1.5 * 5))
        accum += float(vol_quality.loc[i] * 5 + drawdown_quality.loc[i] * 5)
        total = min(100.0, max(0.0, liq + mom + trend + breakout + accum))
        explanations = _explanations(liq, mom, trend, breakout, accum)
        flags = _risk_flags(item)
        rows.append((
            item.ticker, round(total, 1), round(liq, 1), round(mom, 1), round(trend, 1),
            round(breakout, 1), round(accum, 1), _finite(item.rel20), _finite(item.rel60),
            _finite(item.rel120), _finite(item.med20), json.dumps(explanations), json.dumps(flags),
        ))
    db.replace_growth_scores(conn, date_str, rows)
    conn.execute(
        "DELETE FROM narratives WHERE (kind='aftermarket' AND date=?) "
        "OR (kind='premarket' AND date>?)", (date_str, date_str)
    )
    conn.commit()
    return len(rows)


def latest(conn: sqlite3.Connection, limit: int = 20, min_score: float | None = None,
           date_str: str | None = None) -> tuple[str, list[GrowthCandidate]]:
    if date_str is None:
        row = conn.execute("SELECT MAX(date) AS date FROM growth_scores").fetchone()
        date_str = row["date"] if row and row["date"] else ""
    floor = settings.potential_growth_min_score if min_score is None else min_score
    rows = db.growth_rows(conn, date_str, limit, floor) if date_str else []
    return date_str, [_candidate(r) for r in rows]


def coverage(conn: sqlite3.Connection, date_str: str) -> tuple[int, int, float]:
    total = conn.execute(
        "SELECT COUNT(*) FROM universe_eligibility WHERE date=?", (date_str,)
    ).fetchone()[0]
    current = conn.execute(
        "SELECT COUNT(*) FROM universe_eligibility WHERE date=? "
        "AND exclusion_reason!='data tanggal laporan tidak tersedia'", (date_str,)
    ).fetchone()[0]
    return current, total, (current / total if total else 0.0)


def _liquidity_stats(df: pd.DataFrame, ihsg: pd.DataFrame) -> dict:
    calendar = ihsg.tail(60).index
    aligned = df.reindex(calendar)
    volume = aligned["volume"].fillna(0) if "volume" in aligned else pd.Series(0, index=calendar)
    value = (aligned["close"] * volume).fillna(0) if "close" in aligned else volume
    return {
        "traded20": int((volume.tail(20) > 0).sum()),
        "traded60": int((volume > 0).sum()),
        "med20": _finite(value.tail(20).median()),
        "med60": _finite(value.median()),
    }


def _raw_metrics(df: pd.DataFrame, ihsg: pd.DataFrame, date_str: str,
                 stats: dict) -> tuple[dict | None, str]:
    if df.empty or df.index[-1].strftime("%Y-%m-%d") != date_str:
        return None, "data tanggal laporan tidak tersedia"
    if len(df) < settings.liquidity_min_history:
        return None, "histori kurang"
    if float(df.iloc[-1]["close"]) < settings.liquidity_min_close:
        return None, "harga di bawah minimum"
    traded20 = stats["traded20"]
    traded60 = stats["traded60"]
    if traded20 < settings.liquidity_min_traded_20 or traded60 < settings.liquidity_min_traded_60:
        return None, "frekuensi perdagangan rendah"
    if (stats["med20"] or 0) < settings.liquidity_min_value_20:
        return None, "nilai transaksi 20D rendah"
    if (stats["med60"] or 0) < settings.liquidity_min_value_60:
        return None, "nilai transaksi 60D rendah"
    if (df.tail(60)["close"].fillna(0) <= 0).any() or float(df.iloc[-1]["volume"]) <= 0:
        return None, "harga/volume tidak valid"
    if len(ihsg) < 121 or ihsg.index[-1].strftime("%Y-%m-%d") != date_str:
        return None, "data IHSG pembanding tidak cukup"

    c = df["close"]
    market = ihsg["close"]
    ret = lambda s, n: float(s.iloc[-1] / s.iloc[-n - 1] - 1) * 100  # noqa: E731
    returns = c.pct_change().dropna()
    prev20 = float(df["high"].shift(1).tail(20).max())
    prev60 = float(df["high"].shift(1).tail(60).max())
    tail20 = df.tail(20)
    up = tail20["close"].diff() > 0
    up_share = float(tail20.loc[up, "volume"].sum() / tail20["volume"].sum())
    peak = c.tail(120).cummax()
    drawdown = float(abs((c.tail(120) / peak - 1).min()))
    return {
        "close": float(c.iloc[-1]), "sma50": float(c.tail(50).mean()),
        "sma200": float(c.tail(200).mean()), "high52": float(df["high"].tail(252).max()),
        "rel20": ret(c, 20) - ret(market, 20), "rel60": ret(c, 60) - ret(market, 60),
        "rel120": ret(c, 120) - ret(market, 120), "ret20": ret(c, 20),
        "prior20": prev20, "prior60": prev60,
        "volume_x": float(df["volume"].iloc[-1] / df["volume"].tail(20).mean()),
        "volume_ratio_5_20": float(df["volume"].tail(5).mean() / df["volume"].tail(20).mean()),
        "up_volume_share": up_share, "volatility": float(returns.tail(20).std() * np.sqrt(252)),
        "drawdown": drawdown, "move1": abs(ret(c, 1)), "move5": abs(ret(c, 5)),
        "continuity_gaps": 60 - traded60,
    }, ""


def _trend_score(r) -> float:
    return float((5 if r.close > r.sma50 else 0) + (7 if r.close > r.sma200 else 0)
                 + (4 if r.sma50 > r.sma200 else 0)
                 + (4 if r.close >= .75 * r.high52 else 0))


def _breakout_score(r) -> float:
    score = 0.0
    score += 5 if r.close >= r.prior20 else 3 if r.close >= .98 * r.prior20 else 0
    score += 6 if r.close >= r.prior60 else 3 if r.close >= .98 * r.prior60 else 0
    score += min(4.0, max(0.0, r.volume_x / 1.5 * 4))
    return score


def _explanations(liq: float, mom: float, trend: float, breakout: float,
                  accum: float) -> list[str]:
    labels = [(liq / 20, "likuiditas kuat"), (mom / 25, "unggul relatif vs IHSG"),
              (trend / 20, "tren sehat"), (breakout / 15, "dekat/menembus breakout"),
              (accum / 20, "akumulasi dan profil risiko baik")]
    return [label for _, label in sorted(labels, reverse=True)[:2]]


def _risk_flags(r) -> list[str]:
    flags = []
    if r.move1 >= 15:
        flags.append("gerak 1D ekstrem")
    if r.move5 >= 40:
        flags.append("gerak 5D ekstrem")
    if r.volatility >= .60:
        flags.append("volatilitas tinggi")
    if r.drawdown >= .35:
        flags.append("drawdown >35%")
    if getattr(r, "continuity_gaps", 0) >= 5:
        flags.append("kontinuitas data abnormal")
    return flags


def _candidate(r: sqlite3.Row) -> GrowthCandidate:
    return GrowthCandidate(
        from_yf(r["ticker"]), r["total"], r["liquidity"], r["momentum"], r["trend"],
        r["breakout"], r["accumulation_risk"], r["rel_60"], r["median_value_20"],
        json.loads(r["explanations"]), json.loads(r["risk_flags"]),
    )


def _finite(v) -> float | None:
    return None if v is None or pd.isna(v) or not np.isfinite(v) else float(v)
