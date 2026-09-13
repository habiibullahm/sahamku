"""Rekap mingguan: performa IHSG & saham seminggu, dan akurasi sinyal minggu ini."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from sahamku import db
from sahamku.analysis.aftermarket import Mover
from sahamku.universe import IHSG, from_yf, scan_tickers


@dataclass
class SignalHit:
    code: str
    date: str
    rating: str
    ret: float  # % dari close tanggal sinyal ke close akhir minggu


@dataclass
class WeeklyReport:
    week_start: str
    week_end: str
    days: int
    ihsg_start: float | None
    ihsg_end: float | None
    ihsg_pct: float | None
    ihsg_high: float | None
    ihsg_low: float | None
    gainers: list[Mover]
    losers: list[Mover]
    n_bullish: int
    n_bearish: int
    bull_hits: list[SignalHit] = field(default_factory=list)
    bear_hits: list[SignalHit] = field(default_factory=list)

    @property
    def bull_hit_rate(self) -> float | None:
        return _rate([h.ret > 0 for h in self.bull_hits])

    @property
    def bear_hit_rate(self) -> float | None:
        return _rate([h.ret < 0 for h in self.bear_hits])


def _rate(flags: list[bool]) -> float | None:
    return None if not flags else sum(flags) / len(flags) * 100


def week_bounds(ref: date | None = None) -> tuple[date, date]:
    """Senin–Jumat dari minggu yang memuat `ref` (default: hari ini)."""
    ref = ref or date.today()
    monday = ref - timedelta(days=ref.weekday())
    return monday, monday + timedelta(days=4)


def build(conn: sqlite3.Connection, ref: date | None = None, top_n: int = 5
          ) -> WeeklyReport | None:
    mon, fri = week_bounds(ref)
    days = db.trading_dates_between(conn, mon.isoformat(), fri.isoformat())
    if len(days) < 2:
        return None
    first, last = days[0], days[-1]

    # Titik awal = close hari bursa terakhir SEBELUM minggu ini (agar return Senin ikut)
    prev_days = db.trading_dates_between(
        conn, (mon - timedelta(days=10)).isoformat(), (mon - timedelta(days=1)).isoformat())
    base = prev_days[-1] if prev_days else first

    ihsg0, ihsg1 = db.close_at(conn, IHSG, base), db.close_at(conn, IHSG, last)
    ihsg_df = db.load_ohlcv(conn, IHSG)
    wk = ihsg_df.loc[first:last] if not ihsg_df.empty else ihsg_df

    movers: list[Mover] = []
    for t in scan_tickers(conn, last):
        c0, c1 = db.close_at(conn, t, base), db.close_at(conn, t, last)
        if c0 and c1:
            movers.append(Mover(from_yf(t), c1, (c1 / c0 - 1) * 100, 0.0))
    movers.sort(key=lambda m: m.pct, reverse=True)

    # Akurasi: rating non-netral dari hari-hari sebelum hari terakhir → return ke close akhir minggu
    bull, bear, n_bull, n_bear = [], [], 0, 0
    for r in db.ratings_between(conn, first, last):
        if r["rating"] == "bullish":
            n_bull += 1
        else:
            n_bear += 1
        if r["date"] == last:
            continue
        c0, c1 = db.close_at(conn, r["ticker"], r["date"]), db.close_at(conn, r["ticker"], last)
        if not c0 or not c1:
            continue
        hit = SignalHit(from_yf(r["ticker"]), r["date"], r["rating"], (c1 / c0 - 1) * 100)
        (bull if r["rating"] == "bullish" else bear).append(hit)

    return WeeklyReport(
        week_start=first, week_end=last, days=len(days),
        ihsg_start=ihsg0, ihsg_end=ihsg1,
        ihsg_pct=(ihsg1 / ihsg0 - 1) * 100 if ihsg0 and ihsg1 else None,
        ihsg_high=float(wk["high"].max()) if len(wk) else None,
        ihsg_low=float(wk["low"].min()) if len(wk) else None,
        gainers=movers[:top_n], losers=list(reversed(movers[-top_n:])) if movers else [],
        n_bullish=n_bull, n_bearish=n_bear, bull_hits=bull, bear_hits=bear,
    )
