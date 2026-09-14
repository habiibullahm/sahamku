"""Ingestion OHLCV harian dari Yahoo Finance."""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from sahamku import db
from sahamku.config import settings
from sahamku.universe import IHSG, all_eod_tickers

log = logging.getLogger(__name__)

COLS = ["open", "high", "low", "close", "volume"]


def fetch_history(tickers: list[str], start: date | None = None, period: str | None = None
                  ) -> dict[str, pd.DataFrame]:
    """Download batch. Return {ticker: df(open..volume)}. Ticker gagal dilewati."""
    kwargs = {"period": period} if period else {"start": start}
    raw = yf.download(
        tickers, group_by="ticker", auto_adjust=False, threads=False,
        progress=False, **kwargs,
    )
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    multi = isinstance(raw.columns, pd.MultiIndex)
    for t in tickers:
        try:
            df = raw[t] if multi else raw
        except KeyError:
            log.warning("no data for %s", t)
            continue
        df = df.rename(columns=str.lower)
        if not set(COLS).issubset(df.columns):
            log.warning("kolom tidak lengkap untuk %s", t)
            continue
        df = df[COLS].dropna(subset=["close"])
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        if not df.empty:
            out[t] = df
    return out


def ingest(conn: sqlite3.Connection, tickers: list[str] | None = None,
           lookback_days: int = 10, table: str = "ohlcv") -> dict[str, int]:
    """Tarik N hari terakhir dan upsert. Return {ticker: rows}."""
    tickers = tickers or all_eod_tickers(conn)
    start = date.today() - timedelta(days=lookback_days)
    counts: dict[str, int] = {}
    batch_size = max(1, settings.eod_batch_size)
    for i in range(0, len(tickers), batch_size):
        data = fetch_history(tickers[i:i + batch_size], start=start)
        counts.update({t: db.upsert_ohlcv(conn, t, df, table=table)
                       for t, df in data.items()})
        conn.commit()
        if i + batch_size < len(tickers):
            time.sleep(max(0.0, settings.eod_batch_delay_seconds))
    log.info("ingested %d/%d tickers into %s", len(counts), len(tickers), table)
    return counts


def backfill(conn: sqlite3.Connection, tickers: list[str] | None = None,
             period: str = "3y", table: str = "ohlcv") -> dict[str, int]:
    tickers = tickers or all_eod_tickers(conn)
    counts: dict[str, int] = {}
    # batch 15 ticker supaya request tidak terlalu besar
    for i in range(0, len(tickers), 15):
        chunk = tickers[i:i + 15]
        data = fetch_history(chunk, period=period)
        for t, df in data.items():
            counts[t] = db.upsert_ohlcv(conn, t, df, table=table)
        conn.commit()
        log.info("backfill batch %d: %d tickers", i // 15 + 1, len(data))
    return counts


def validate_eod(conn: sqlite3.Connection, trading_date: date,
                 tickers: list[str] | None = None) -> tuple[bool, list[str]]:
    """Cek semua ticker punya bar untuk trading_date. Return (lengkap?, missing)."""
    tickers = tickers or all_eod_tickers(conn)
    have = db.tickers_with_date(conn, trading_date.isoformat())
    missing = [t for t in tickers if t not in have]
    stocks = [t for t in tickers if t != IHSG]
    covered = sum(t in have for t in stocks)
    ratio = covered / len(stocks) if stocks else 0.0
    return (IHSG in have and ratio >= settings.universe_min_coverage, missing)
