"""Snapshot intraday (delayed ~15 menit dari Yahoo): bar harian parsial hari ini per ticker."""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, time, timedelta

import pandas as pd

from sahamku import db
from sahamku.config import TZ
from sahamku.ingestion.eod import fetch_history
from sahamku.universe import IHSG, scan_tickers

log = logging.getLogger(__name__)

SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(16, 0)  # termasuk pre-closing/post-trading
CACHE_MAX_AGE = timedelta(minutes=5)
_snapshot_lock = threading.Lock()
_last_manual_attempt: datetime | None = None


def in_session(now: datetime | None = None) -> bool:
    now = now or datetime.now(TZ)
    return now.weekday() < 5 and SESSION_OPEN <= now.time() <= SESSION_CLOSE


def snapshot(conn: sqlite3.Connection, tickers: list[str] | None = None,
             now: datetime | None = None) -> int:
    """Ambil bar hari ini (parsial) dan simpan ke tabel intraday. Return jumlah ticker."""
    tickers = tickers or [
        IHSG, *scan_tickers(conn, db.latest_date(conn, ticker=IHSG))
    ]
    now = now or datetime.now(TZ)
    today = now.date()
    ts = now.isoformat(timespec="minutes")
    n = 0
    for i in range(0, len(tickers), 50):
        try:
            data = fetch_history(tickers[i:i + 50], period="5d")
        except Exception:
            log.warning("intraday fetch gagal untuk batch %d", i // 50 + 1, exc_info=True)
            continue
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


def is_fresh(row: sqlite3.Row | None, now: datetime | None = None) -> bool:
    """True bila snapshot berasal dari hari ini dan belum melewati masa cache."""
    if not row:
        return False
    now = now or datetime.now(TZ)
    if row["date"] != now.date().isoformat():
        return False
    try:
        observed = datetime.fromisoformat(row["ts"])
    except (TypeError, ValueError):
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=TZ)
    age = now - observed
    return timedelta() <= age <= CACHE_MAX_AGE


def refresh_if_stale(conn: sqlite3.Connection, tickers: list[str],
                     now: datetime | None = None) -> bool:
    """Refresh ticker yang diminta sekali bila cache intraday tidak lagi segar.

    Dipakai command manual agar tidak mengunduh seluruh universe dan tidak memicu
    request Yahoo paralel saat banyak pengguna meminta snapshot bersamaan.
    """
    global _last_manual_attempt

    now = now or datetime.now(TZ)
    unique = list(dict.fromkeys(tickers))
    if not unique or not in_session(now):
        return False

    date_str = now.date().isoformat()
    if all(is_fresh(db.intraday_get(conn, ticker, date_str), now) for ticker in unique):
        return False

    with _snapshot_lock:
        if (_last_manual_attempt is not None
                and timedelta() <= now - _last_manual_attempt <= CACHE_MAX_AGE):
            return False
        if all(is_fresh(db.intraday_get(conn, ticker, date_str), now) for ticker in unique):
            return False
        _last_manual_attempt = now
        snapshot(conn, unique, now=now)
        return True
