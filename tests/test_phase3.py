import numpy as np
import pandas as pd

from sahamku import db, levels
from sahamku.config import settings


def test_levels_basic():
    # harga zigzag: swing low 90, swing high 110, close 100
    close = np.array([100, 95, 90, 95, 100, 105, 110, 105, 100, 98, 100, 101, 100, 99, 100],
                     dtype=float)
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close,
                       "volume": 1.0}, index=pd.bdate_range("2026-01-01", periods=len(close)))
    lv = levels.compute(df, lookback=50, window=2)
    assert lv.supports and lv.supports[0] < 100
    assert lv.resistances and lv.resistances[0] > 100
    assert "S1" in levels.describe(lv) and "R1" in levels.describe(lv)


def test_prefs_and_recipients(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "p.db")
    db.init_db()
    with db.db() as c:
        db.upsert_user(c, 1, "a")
        db.upsert_user(c, 2, "b")
        assert db.prefs_get(c, 1) == {k: True for k in db.PREF_KEYS}
        assert db.prefs_toggle(c, 1, "premarket") is False
        assert db.recipients(c, "premarket") == [2]
        assert sorted(db.recipients(c, "aftermarket")) == [1, 2]
        db.set_subscribed(c, 2, False)
        assert db.recipients(c, "aftermarket") == [1]


def test_ask_history(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "h.db")
    db.init_db()
    with db.db() as c:
        db.ask_history_add(c, 5, "user", "kenapa BBCA turun?")
        db.ask_history_add(c, 5, "assistant", "karena ...")
        assert db.ask_history_recent(c, 5) == [("user", "kenapa BBCA turun?"),
                                               ("assistant", "karena ...")]
        db.ask_history_clear(c, 5)
        assert db.ask_history_recent(c, 5) == []
