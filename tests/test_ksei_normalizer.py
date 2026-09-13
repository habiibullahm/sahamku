import zipfile

import pytest

from scripts.normalize_ksei_master import normalize, write_csv
from scripts.update_universe import load

HEADER = "Date|Code|Description|Type|Status|Stock Exchange|Sector\n"


def master_rows() -> str:
    return HEADER + (
        "31-AUG-2026|AAAA|Alpha Tbk|EQUITY|ACTIVE|IDX|TECHNOLOGY\n"
        "31-AUG-2026|BBBB|Beta Tbk|EQUITY|SUSPENDED|IDX|ENERGY\n"
        "31-AUG-2026|CCCC|Gamma Tbk|WARRANT|ACTIVE|IDX|TECHNOLOGY\n"
        "31-AUG-2026|ABCDE|Long Tbk|EQUITY|ACTIVE|IDX|TECHNOLOGY\n"
        "31-AUG-2026|DDDD|Delta Tbk|EQUITY|ACTIVE|OTC|TECHNOLOGY\n"
    )


def test_normalize_ksei_text_and_output_is_importable(tmp_path):
    source = tmp_path / "master.txt"
    source.write_text(master_rows(), encoding="utf-8")

    rows, excluded = normalize(source)

    assert rows == [{
        "code": "AAAA", "name": "Alpha Tbk", "sector": "TECHNOLOGY",
        "board": "Unknown", "instrument_type": "stock", "status": "active",
        "source_date": "2026-08-31",
    }]
    assert excluded == {"inactive": 1, "non_equity": 1, "invalid_code": 1, "non_idx": 1}
    output = tmp_path / "idx-stocks.csv"
    write_csv(rows, output)
    assert load(output) == rows


def test_normalize_ksei_zip(tmp_path):
    source = tmp_path / "master.txt.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("master.txt", master_rows())
    rows, _ = normalize(source)
    assert [row["code"] for row in rows] == ["AAAA"]


def test_normalize_joins_ksei_unquoted_wrapped_description(tmp_path):
    source = tmp_path / "master.txt"
    source.write_text(
        HEADER
        + "31-AUG-2026|AAAA|Alpha\n"
        + "Tbk|EQUITY|ACTIVE|IDX|TECHNOLOGY\n",
        encoding="utf-8",
    )
    rows, _ = normalize(source)
    assert rows[0]["name"] == "Alpha Tbk"


def test_normalize_rejects_multiple_source_dates(tmp_path):
    source = tmp_path / "master.txt"
    source.write_text(
        HEADER
        + "31-AUG-2026|AAAA|Alpha Tbk|EQUITY|ACTIVE|IDX|TECHNOLOGY\n"
        + "30-AUG-2026|BBBB|Beta Tbk|EQUITY|ACTIVE|IDX|TECHNOLOGY\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="satu source date"):
        normalize(source)
