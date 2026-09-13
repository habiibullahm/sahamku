import sqlite3
from datetime import date

from sahamku import db
from sahamku.ingestion.eod import validate_eod
from sahamku.universe import IHSG


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


def test_eod_requires_ihsg_and_ninety_percent_coverage():
    conn = _conn()
    day = "2026-09-14"
    stocks = [f"AA{i:02d}.JK" for i in range(10)]
    tickers = [IHSG, *stocks]
    row = lambda ticker: (ticker, day, 1, 1, 1, 1, 1)  # noqa: E731
    conn.executemany("INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?)",
                     [row(IHSG), *(row(t) for t in stocks[:9])])
    ok, _ = validate_eod(conn, date.fromisoformat(day), tickers)
    assert ok
    conn.execute("DELETE FROM ohlcv WHERE ticker=?", (stocks[8],))
    assert not validate_eod(conn, date.fromisoformat(day), tickers)[0]
    conn.execute("DELETE FROM ohlcv WHERE ticker=?", (IHSG,))
    assert not validate_eod(conn, date.fromisoformat(day), tickers)[0]
