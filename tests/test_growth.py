import sqlite3

import numpy as np
import pandas as pd

from sahamku import db
from sahamku.analysis import growth
from sahamku.config import settings


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


def _prices(index, start, daily, volume):
    close = start * np.cumprod(np.full(len(index), 1 + daily))
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * .99,
        "close": close, "volume": volume,
    }, index=index)


def test_liquid_filter_and_growth_score(monkeypatch):
    monkeypatch.setattr(settings, "universe", "liquid")
    idx = pd.bdate_range("2025-01-01", periods=260)
    conn = _conn()
    conn.executemany(
        "INSERT INTO securities VALUES (?,?,?,?,?,?,?,?)",
        [("AAAA", "A", "Tech", "Main", "stock", "active", "2026-01-01", "now"),
         ("BBBB", "B", "Tech", "Main", "stock", "active", "2026-01-01", "now")],
    )
    db.upsert_ohlcv(conn, "^JKSE", _prices(idx, 6000, .0002, 1))
    db.upsert_ohlcv(conn, "AAAA.JK", _prices(idx, 500, .0015, 20_000_000))
    db.upsert_ohlcv(conn, "BBBB.JK", _prices(idx, 500, .0005, 1_000))

    assert growth.compute_and_store(conn) == 1
    day = idx[-1].strftime("%Y-%m-%d")
    eligible = db.eligible_tickers(conn, day)
    assert eligible == ["AAAA.JK"]
    excluded = conn.execute(
        "SELECT exclusion_reason FROM universe_eligibility WHERE ticker='BBBB.JK'"
    ).fetchone()[0]
    assert "nilai transaksi" in excluded
    rows = db.growth_rows(conn, day)
    assert len(rows) == 1 and 0 <= rows[0]["total"] <= 100
    assert rows[0]["explanations"] != "[]"


def test_risk_flags():
    row = type("R", (), {"move1": 16, "move5": 45, "volatility": .7, "drawdown": .4})()
    assert growth._risk_flags(row) == [
        "gerak 1D ekstrem", "gerak 5D ekstrem", "volatilitas tinggi", "drawdown >35%"
    ]
