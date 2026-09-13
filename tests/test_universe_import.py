import sqlite3

import pytest

from sahamku import db
from scripts.update_universe import import_rows, load


def test_import_accepts_normalized_common_stocks(tmp_path):
    path = tmp_path / "idx.csv"
    path.write_text(
        "code,name,sector,board,instrument_type,status\n"
        "AAAA,Alpha,Technology,Main,stock,active\n"
        "BBBB,Beta,Energy,Development,common stock,suspended\n",
        encoding="utf-8",
    )
    rows = load(path)
    assert [r["code"] for r in rows] == ["AAAA", "BBBB"]
    assert rows[1]["status"] == "suspended"


@pytest.mark.parametrize(
    "body",
    [
        "AAAA,Alpha,Technology,Main,stock,active\nAAAA,Again,Energy,Main,stock,active\n",
        "ABC,Alpha,Technology,Main,stock,active\n",
        "AAAA,Alpha,Technology,Main,etf,active\n",
    ],
)
def test_import_rejects_bad_master(tmp_path, body):
    path = tmp_path / "idx.csv"
    path.write_text(
        "code,name,sector,board,instrument_type,status\n" + body, encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load(path)


def test_large_change_keeps_last_good_master():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    original = [{"code": "AAAA", "name": "A", "sector": "Tech", "board": "Main",
                 "instrument_type": "stock", "status": "active"}]
    import_rows(conn, original, "2026-09-01")
    changed = original + [{"code": "BBBB", "name": "B", "sector": "Energy",
                           "board": "Main", "instrument_type": "stock", "status": "active"}]
    with pytest.raises(ValueError):
        import_rows(conn, changed, "2026-09-02")
    assert conn.execute("SELECT code FROM securities").fetchone()[0] == "AAAA"


def test_import_invalidates_prior_liquid_snapshots():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    rows = [{"code": "AAAA", "name": "A", "sector": "Tech", "board": "Main",
             "instrument_type": "stock", "status": "active"}]
    conn.execute("INSERT INTO universe_eligibility VALUES (?,?,?,?,?,?,?,?,?)",
                 ("2026-09-01", "OLD.JK", 1, 250, 20, 60, 10, 10, ""))
    conn.execute("INSERT INTO growth_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("2026-09-01", "OLD.JK", 80, 1, 1, 1, 1, 1, 1, 1, 1, 1, "[]", "[]"))
    import_rows(conn, rows, "2026-09-02")
    assert conn.execute("SELECT COUNT(*) FROM universe_eligibility").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM growth_scores").fetchone()[0] == 0
