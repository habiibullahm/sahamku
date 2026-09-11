"""Orkestrasi: OHLCV -> indikator -> sinyal -> rating, per ticker, simpan ke DB."""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from sahamku import db
from sahamku.indicators.technical import compute
from sahamku.signals.rules import evaluate_latest
from sahamku.signals.scoring import score_and_rate
from sahamku.universe import ALL_EOD_TICKERS, STOCK_TICKERS

log = logging.getLogger(__name__)


def load_joined(conn: sqlite3.Connection, ticker: str, limit: int | None = None) -> pd.DataFrame:
    """OHLCV + indikator (dihitung ulang dari OHLCV, bukan dari tabel indicators)."""
    ohlcv = db.load_ohlcv(conn, ticker)
    if ohlcv.empty:
        return ohlcv
    joined = ohlcv.join(compute(ohlcv))
    return joined.tail(limit) if limit else joined


def process_ticker(conn: sqlite3.Connection, ticker: str, store_indicator_rows: int = 5) -> None:
    ohlcv = db.load_ohlcv(conn, ticker)
    if len(ohlcv) < 30:
        log.warning("%s: data terlalu sedikit (%d bar)", ticker, len(ohlcv))
        return
    ind = compute(ohlcv)
    db.upsert_indicators(conn, ticker, ind.tail(store_indicator_rows))
    joined = ohlcv.join(ind)
    sigs = evaluate_latest(joined)
    date_str = joined.index[-1].strftime("%Y-%m-%d")
    db.replace_signals(conn, ticker, date_str, [(s.rule, s.direction, s.detail) for s in sigs])
    sc, rt = score_and_rate(sigs)
    db.upsert_rating(conn, ticker, date_str, sc, rt)


def ensure_history(conn: sqlite3.Connection, min_bars: int = 250) -> list[str]:
    """Backfill 3 tahun untuk ticker yang belum punya histori (mis. setelah universe diperluas)."""
    from sahamku.ingestion.eod import backfill

    missing = []
    for t in ALL_EOD_TICKERS:
        n = conn.execute("SELECT COUNT(*) FROM ohlcv WHERE ticker=?", (t,)).fetchone()[0]
        if n < min_bars:
            missing.append(t)
    if missing:
        log.info("backfill %d ticker baru: %s", len(missing), ", ".join(missing))
        backfill(conn, missing)
        recompute_all(conn, missing)
    return missing


def recompute_all(conn: sqlite3.Connection, tickers: list[str] | None = None) -> int:
    n = 0
    for t in tickers or STOCK_TICKERS:
        try:
            process_ticker(conn, t)
            n += 1
        except Exception:
            log.exception("gagal proses %s", t)
    conn.commit()
    return n
