import sqlite3

from sahamku import db
from sahamku.config import settings
from sahamku.universe import IDX80, active_codes, scan_tickers, universe_label


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


def test_liquid_falls_back_to_idx80(monkeypatch):
    monkeypatch.setattr(settings, "universe", "liquid")
    conn = _conn()
    assert active_codes(conn) == IDX80
    assert "fallback" in universe_label(conn)


def test_liquid_master_excludes_inactive_and_non_stock(monkeypatch):
    monkeypatch.setattr(settings, "universe", "liquid")
    conn = _conn()
    rows = [
        ("AAAA", "A", "Tech", "Main", "stock", "active", "2026-01-01", "now"),
        ("BBBB", "B", "Tech", "Main", "stock", "suspended", "2026-01-01", "now"),
        ("CCCC", "C", "ETF", "Main", "etf", "active", "2026-01-01", "now"),
    ]
    conn.executemany("INSERT INTO securities VALUES (?,?,?,?,?,?,?,?)", rows)
    assert active_codes(conn) == ["AAAA"]
    assert universe_label(conn) == "universe liquid"


def test_completed_filter_with_zero_eligible_does_not_fallback(monkeypatch):
    monkeypatch.setattr(settings, "universe", "liquid")
    conn = _conn()
    conn.execute(
        "INSERT INTO universe_eligibility VALUES (?,?,?,?,?,?,?,?,?)",
        ("2026-09-11", "AAAA.JK", 0, 250, 10, 30, 1, 1, "likuiditas rendah"),
    )
    assert scan_tickers(conn, "2026-09-11") == []
