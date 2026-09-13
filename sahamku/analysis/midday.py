"""Ringkasan tengah hari (sesi 1) dari snapshot intraday."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sahamku import db
from sahamku.analysis.aftermarket import Mover
from sahamku.universe import IHSG, from_yf, scan_tickers


@dataclass
class MiddayReport:
    date: str
    ts: str
    ihsg_last: float | None
    ihsg_pct: float | None
    ihsg_high: float | None
    ihsg_low: float | None
    advancers: int
    decliners: int
    gainers: list[Mover]
    losers: list[Mover]
    watchlist: dict[str, Mover | None] = field(default_factory=dict)


def build(conn: sqlite3.Connection, watch_codes: list[str] | None = None,
          top_n: int = 5) -> MiddayReport | None:
    rows = db.intraday_all(conn)
    if not rows:
        return None
    by = {r["ticker"]: r for r in rows}
    ihsg = by.get(IHSG)
    movers: list[Mover] = []
    for t in scan_tickers(conn, db.latest_date(conn)):
        r = by.get(t)
        if not r or not r["prev_close"]:
            continue
        pct = (r["last"] / r["prev_close"] - 1) * 100
        movers.append(Mover(from_yf(t), r["last"], pct, r["volume"]))
    movers.sort(key=lambda m: m.pct, reverse=True)
    mv = {m.code: m for m in movers}
    return MiddayReport(
        date=rows[0]["date"], ts=rows[0]["ts"][11:16],
        ihsg_last=ihsg["last"] if ihsg else None,
        ihsg_pct=((ihsg["last"] / ihsg["prev_close"] - 1) * 100
                  if ihsg and ihsg["prev_close"] else None),
        ihsg_high=ihsg["high"] if ihsg else None, ihsg_low=ihsg["low"] if ihsg else None,
        advancers=sum(1 for m in movers if m.pct > 0),
        decliners=sum(1 for m in movers if m.pct < 0),
        gainers=movers[:top_n], losers=list(reversed(movers[-top_n:])) if movers else [],
        watchlist={c: mv.get(c) for c in (watch_codes or [])},
    )
