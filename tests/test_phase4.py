from datetime import datetime

from sahamku import db
from sahamku.analysis.sector import SECTORS, sector_of
from sahamku.config import TZ, settings
from sahamku.ingestion.intraday import in_session
from sahamku.universe import STOCKS


def test_in_session_hours():
    assert in_session(datetime(2026, 9, 14, 9, 30, tzinfo=TZ))       # Senin 09:30
    assert not in_session(datetime(2026, 9, 14, 8, 30, tzinfo=TZ))   # sebelum buka
    assert not in_session(datetime(2026, 9, 14, 16, 30, tzinfo=TZ))  # setelah tutup
    assert not in_session(datetime(2026, 9, 12, 10, 0, tzinfo=TZ))   # Sabtu


def test_sector_mapping_covers_universe():
    unmapped = [c for c in STOCKS if sector_of(c) is None]
    assert unmapped == [], unmapped
    dup = [c for codes in SECTORS.values() for c in codes]
    assert len(dup) == len(set(dup))


def test_plan_and_migration(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "m.db")
    db.init_db()
    with db.db() as c:
        db.upsert_user(c, 1, "a")
        assert db.plan_get(c, 1) == "free"
        assert db.plan_set(c, 1, "pro")
        assert db.plan_get(c, 1) == "pro"
        assert not db.plan_set(c, 99, "pro")
        assert "midday" in db.prefs_get(c, 1)
