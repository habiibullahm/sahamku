"""Snapshot intraday (delayed ~15 menit dari Yahoo): bar harian parsial hari ini per ticker."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, time

import pandas as pd

from sahamku import db
from sahamku.config import TZ
from sahamku.ingestion.eod import fetch_history
from sahamku.universe import IHSG, scan_tickers

log = logging.getLogger(__name__)

SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(16, 0)  # termasuk pre-closing/post-trading


def in_session(now: datetime | None = None) -> bool:
    now = now or datetime.now(TZ)
    return now.weekday() < 5 and SESSION_OPEN <= now.time() <= SESSION_CLOSE


def snapshot(conn: sqlite3.Connection, tickers: list[str] | None = None) -> int:
    """Ambil bar hari ini (parsial) dan simpan ke tabel intraday. Return jumlah ticker."""
    tickers = tickers or [
        IHSG, *scan_tickers(conn, db.latest_date(conn, ticker=IHSG))
    ]
    today = datetime.now(TZ).date()
    ts = datetime.now(TZ).isoformat(timespec="minutes")
    n = 0
    for i in range(0, len(tickers), 50):
        data = fetch_history(tickers[i:i + 50], period="5d")
        for t, df in data.items():
            last_idx = df.index[-1]
            if pd.Timestamp(last_idx).date() != today:
                continue  # belum ada bar hari ini (pre-open / libur)
            r = df.iloc[-1]
            prev = float(df["close"].iloc[-2]) if len(df) > 1 else None
            db.intraday_upsert(conn, t, today.isoformat(), ts, float(r["open"]),
                               float(r["high"]), float(r["low"]), float(r["close"]),
                               float(r["volume"]), prev)
            n += 1
    conn.commit()
    log.info("intraday snapshot: %d/%d ticker", n, len(tickers))
    return n
