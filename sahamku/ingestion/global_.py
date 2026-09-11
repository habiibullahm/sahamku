"""Ingestion aset global (indeks, komoditas, kurs) untuk analisis pre-market."""

from __future__ import annotations

import logging
import sqlite3

from sahamku.ingestion.eod import backfill, ingest
from sahamku.universe import GLOBAL_TICKERS

log = logging.getLogger(__name__)


def ingest_global(conn: sqlite3.Connection, lookback_days: int = 10) -> dict[str, int]:
    return ingest(conn, list(GLOBAL_TICKERS), lookback_days=lookback_days, table="global_ohlcv")


def backfill_global(conn: sqlite3.Connection, period: str = "1y") -> dict[str, int]:
    return backfill(conn, list(GLOBAL_TICKERS), period=period, table="global_ohlcv")
