from datetime import datetime
from io import BytesIO
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import pytest
from openpyxl import Workbook

from sahamku import db
from sahamku.analysis import trade_plan
from sahamku.news import idx_disclosures

TZ = ZoneInfo("Asia/Jakarta")


def _conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "idx-disclosures.db")
    db.init_db()
    conn = db.connect()
    conn.execute(
        "INSERT INTO securities VALUES (?,?,?,?,?,?,?,?)",
        ("AAAA", "Alpha", "Energy", "Main", "Stock", "Active", "2026-09-14", "now"),
    )
    conn.commit()
    return conn


def _csv(url: str = "https://www.idx.co.id/disclosures/alpha.pdf") -> bytes:
    return (
        "kode emiten;tanggal publikasi;kategori;judul;tautan;nomor\n"
        f"AAAA;14/09/2026;Kontrak Material;AAAA meraih kontrak baru;{url};IDX-1\n"
    ).encode()


def test_import_csv_creates_auditable_grade_a_catalyst(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    records = idx_disclosures.load_bytes(_csv(), "disclosure.csv")
    observed = datetime.fromisoformat("2026-09-14T10:00:00+07:00")

    assert idx_disclosures.ingest_records(conn, records, observed) == 1
    assert idx_disclosures.ingest_records(conn, records, observed) == 0
    row = conn.execute("SELECT * FROM idx_disclosures").fetchone()
    assert row["ticker"] == "AAAA"
    assert row["observed_at"].startswith("2026-09-14T10:00")

    db.news_set_analysis(conn, row["id"], "AAAA", 1, True)
    db.news_insert(conn, {
        "id": "media-newer", "source": "Media", "title": "AAAA raih kontrak lain",
        "summary": "berita lebih baru", "link": "https://example.com/news",
        "published": "2026-09-14T11:00+07:00",
    }, "AAAA")
    db.news_set_analysis(conn, "media-newer", "AAAA", 1, True)
    conn.commit()
    catalyst = trade_plan.catalyst_for(
        conn, "AAAA", datetime.fromisoformat("2026-09-14T12:00:00+07:00")
    )
    assert catalyst.grade == "A"
    assert catalyst.source == "IDX"
    assert catalyst.observed.startswith("2026-09-14T10:00")


def test_import_rejects_non_idx_url_without_partial_write(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    records = idx_disclosures.load_bytes(
        _csv("https://example.com/not-official.pdf"), "disclosure.csv"
    )
    with pytest.raises(idx_disclosures.DisclosureError, match="bukan domain HTTPS resmi IDX"):
        idx_disclosures.ingest_records(conn, records)
    assert conn.execute("SELECT COUNT(*) FROM idx_disclosures").fetchone()[0] == 0


def test_xlsx_aliases_are_supported():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Ekspor Keterbukaan Informasi Bursa Efek Indonesia"])
    sheet.append(["Dibuat 14 September 2026"])
    sheet.append(["Kode Emiten", "Tanggal", "Jenis Informasi", "Perihal", "Link"])
    sheet.append([
        "AAAA", datetime(2026, 9, 14), "Dividen", "Pembagian dividen",
        "https://idx.co.id/disclosures/dividend.pdf",
    ])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    rows = idx_disclosures.load_bytes(stream.getvalue(), "disclosures.xlsx")
    assert rows[0]["ticker"] == "AAAA"
    assert rows[0]["category"] == "Dividen"


def test_refresh_failure_preserves_last_success(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    db.source_state_set(conn, idx_disclosures.SOURCE, "ok", "manual", success=True)
    conn.commit()
    before = db.source_state_get(conn, idx_disclosures.SOURCE)["last_success"]
    monkeypatch.setattr(
        idx_disclosures.settings,
        "idx_disclosure_url",
        "https://www.idx.co.id/disclosures/export.json",
    )

    def fail(*args, **kwargs):
        raise HTTPError(args[0].full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(idx_disclosures, "urlopen", fail)
    result = idx_disclosures.refresh(conn)
    state = db.source_state_get(conn, idx_disclosures.SOURCE)

    assert result.status == "stale"
    assert state["status"] == "stale"
    assert state["last_success"] == before
