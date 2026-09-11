import pytest

from sahamku import db
from sahamku.config import settings


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    db.init_db()
    yield


def test_subscribe_toggle(tmp_db):
    with db.db() as c:
        db.upsert_user(c, 1, "a")
        assert db.is_subscribed(c, 1)
        db.set_subscribed(c, 1, False)
        assert not db.is_subscribed(c, 1)
        assert db.subscribed_chat_ids(c) == []
        db.upsert_user(c, 1, "a")  # upsert tidak mengubah status
        assert not db.is_subscribed(c, 1)
        db.set_subscribed(c, 1, True)
        assert db.subscribed_chat_ids(c) == [1]


def test_ask_counter(tmp_db):
    with db.db() as c:
        assert db.ask_count_today(c, 7) == 0
        assert db.ask_increment(c, 7) == 1
        assert db.ask_increment(c, 7) == 2
        assert db.ask_count_today(c, 8) == 0
