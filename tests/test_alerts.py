from sahamku import alerts, db
from sahamku.config import settings


def test_parse_price_variants():
    s = alerts.parse("BBCA > 6500")
    assert s.code == "BBCA" and s.metric == "close" and s.op == ">" and s.value == 6500
    s = alerts.parse("tlkm <= 2.500")
    assert s.code == "TLKM" and s.value == 2500
    s = alerts.parse("BBRI close >= 4000")
    assert s.metric == "close" and s.op == ">="


def test_parse_rsi_and_errors():
    s = alerts.parse("BBRI rsi < 30")
    assert s.metric == "rsi" and s.value == 30
    assert isinstance(alerts.parse("BBRI rsi < 150"), str)
    assert isinstance(alerts.parse("ZZZZ > 100"), str)
    assert isinstance(alerts.parse("BBCA 6500"), str)
    assert isinstance(alerts.parse(""), str)


def test_label():
    assert alerts.AlertSpec("BBCA", "close", ">", 6500).label() == "BBCA harga > 6,500"
    assert alerts.AlertSpec("BBRI", "rsi", "<", 30).label() == "BBRI RSI < 30"


def test_db_alert_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "a.db")
    db.init_db()
    with db.db() as c:
        aid = db.alert_add(c, 1, "BBCA", "close", ">", 6500)
        assert db.alert_count(c, 1) == 1
        assert [r["id"] for r in db.alert_list(c, 1)] == [aid]
        assert not db.alert_remove(c, 2, aid)  # chat lain tidak bisa hapus
        db.alert_mark_triggered(c, aid)
        assert db.alert_count(c, 1) == 0
        assert db.alerts_active(c) == []
