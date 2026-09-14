import sqlite3
from datetime import date

import pandas as pd

from sahamku import db
from sahamku.ingestion import eod
from sahamku.report import format as fmt
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
    ok, _ = eod.validate_eod(conn, date.fromisoformat(day), tickers)
    assert ok
    conn.execute("DELETE FROM ohlcv WHERE ticker=?", (stocks[8],))
    assert not eod.validate_eod(conn, date.fromisoformat(day), tickers)[0]
    conn.execute("DELETE FROM ohlcv WHERE ticker=?", (IHSG,))
    assert not eod.validate_eod(conn, date.fromisoformat(day), tickers)[0]


def test_eod_state_and_pending_message_are_explicit():
    conn = _conn()
    db.eod_state_set(conn, "2026-09-14", "retrying", 2, 81)
    state = db.eod_state_get(conn, "2026-09-14")
    assert state["attempt"] == 2
    assert state["missing_count"] == 81
    text = fmt.eod_pending("2026-09-14", 81)
    assert "MENUNGGU DATA TERBARU" in text
    assert "2026-09-14" in text


def test_ingest_uses_small_spaced_batches(monkeypatch):
    conn = _conn()
    calls = []

    def fake_fetch(tickers, **kwargs):
        calls.append(tickers)
        frame = pd.DataFrame(
            {"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]},
            index=pd.DatetimeIndex(["2026-09-14"]),
        )
        return {ticker: frame for ticker in tickers}

    monkeypatch.setattr(eod, "fetch_history", fake_fetch)
    monkeypatch.setattr(eod.time, "sleep", lambda _: None)
    monkeypatch.setattr(eod.settings, "eod_batch_size", 2)
    monkeypatch.setattr(eod.settings, "eod_batch_delay_seconds", 0.1)
    counts = eod.ingest(conn, ["AAAA.JK", "BBBB.JK", "CCCC.JK"], lookback_days=1)

    assert [len(chunk) for chunk in calls] == [2, 1]
    assert set(counts) == {"AAAA.JK", "BBBB.JK", "CCCC.JK"}
