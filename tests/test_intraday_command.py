import sqlite3
from datetime import datetime

from sahamku import db
from sahamku.config import TZ
from sahamku.ingestion import intraday
from sahamku.report import format as fmt
from tests.test_html_safety import assert_telegram_html


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


def _put(conn, ticker: str, ts: str) -> None:
    conn.execute(
        "INSERT INTO intraday VALUES (?,?,?,?,?,?,?,?,?)",
        (ticker, "2026-09-14", ts, 6500, 6600, 6450, 6550, 1_000_000, 6500),
    )


def test_intraday_cache_freshness_and_targeted_refresh(monkeypatch):
    conn = _conn()
    now = datetime(2026, 9, 14, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(intraday, "_last_manual_attempt", None)
    _put(conn, "^JKSE", "2026-09-14T09:58+07:00")
    assert intraday.is_fresh(db.intraday_get(conn, "^JKSE", "2026-09-14"), now)

    calls: list[list[str]] = []
    monkeypatch.setattr(intraday, "in_session", lambda _: True)
    monkeypatch.setattr(intraday, "snapshot", lambda _c, tickers, now: calls.append(tickers))
    assert not intraday.refresh_if_stale(conn, ["^JKSE"], now)
    assert calls == []

    _put(conn, "BBCA.JK", "2026-09-14T09:40+07:00")
    assert intraday.refresh_if_stale(conn, ["^JKSE", "BBCA.JK"], now)
    assert calls == [["^JKSE", "BBCA.JK"]]
    assert not intraday.refresh_if_stale(conn, ["BBCA.JK"], now)
    assert calls == [["^JKSE", "BBCA.JK"]]

    monkeypatch.setattr(intraday, "in_session", lambda _: False)
    assert not intraday.refresh_if_stale(conn, ["^JKSE"], now)
    assert calls == [["^JKSE", "BBCA.JK"]]


def test_intraday_formatter_marks_status_and_escapes_html():
    ihsg = fmt.ihsg_snapshot(
        "2026-09-14", 6550, 0.77, 10, {}, 6400, 6700, "turun <tajam>",
        market_status="🟢 LIVE", observed_at="Observasi 2026-09-14 10:00 WIB",
        intraday_low=6450, intraday_high=6600,
    )
    watchlist = fmt.watchlist_snapshot(
        [("AA<BB", 100, 1.0, "penutupan 2026-09-11")],
        "⚪ PENUTUPAN TERAKHIR", "Penutupan 2026-09-11",
    )
    assert "LIVE" in ihsg and "Range hari ini" in ihsg
    assert "PENUTUPAN TERAKHIR" in watchlist and "AA&lt;BB" in watchlist
    assert_telegram_html(ihsg)
    assert_telegram_html(watchlist)


def test_scheduled_snapshot_keeps_active_plan_tickers(monkeypatch):
    conn = _conn()
    now = datetime(2026, 9, 14, 10, 0, tzinfo=TZ)
    batches = []
    monkeypatch.setattr(intraday, "scan_tickers", lambda *_: ["SCAN.JK"])
    monkeypatch.setattr(db, "trade_plans_active", lambda _: [{"ticker": "PLAN.JK"}])
    monkeypatch.setattr(
        intraday, "fetch_history", lambda tickers, period: batches.append(tickers) or {}
    )
    assert intraday.snapshot(conn, now=now) == 0
    assert batches == [["^JKSE", "SCAN.JK", "PLAN.JK"]]
