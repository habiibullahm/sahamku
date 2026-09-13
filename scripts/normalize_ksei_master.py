"""Normalize KSEI Master File Efek into Sahamku's securities-master CSV.

The KSEI archive contains many security classes.  This script keeps only active
IDX equities with a four-letter ticker, which is the closest KSEI-only proxy for
ordinary listed shares.  KSEI does not publish the IDX board in this file, so
the generated ``board`` value is explicitly ``Unknown``.

Usage:
    python scripts/normalize_ksei_master.py StatisEfekYYYYMMDD.txt.zip
    python scripts/normalize_ksei_master.py master.txt --output idx-stocks.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

OUTPUT_COLUMNS = [
    "code",
    "name",
    "sector",
    "board",
    "instrument_type",
    "status",
    "source_date",
]
CODE = re.compile(r"^[A-Z]{4}$")
RECORD_START = re.compile(r"^\d{2}-[A-Z]{3}-\d{4}\|")
KSEI_REQUIRED = {"Date", "Code", "Description", "Type", "Status", "Stock Exchange", "Sector"}


def _open_master(path: Path) -> io.TextIOBase:
    """Open either the downloaded KSEI ZIP or its extracted pipe-delimited text file."""
    if path.suffix.lower() != ".zip":
        return path.open(encoding="utf-8-sig", newline="")

    archive = zipfile.ZipFile(path)
    members = [entry for entry in archive.infolist() if not entry.is_dir()]
    if len(members) != 1:
        archive.close()
        raise ValueError("arsip KSEI harus berisi tepat satu file master")
    raw = archive.open(members[0])
    # Keep the archive alive until the wrapper is closed.
    wrapper = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    original_close = wrapper.close

    def close() -> None:
        original_close()
        archive.close()

    wrapper.close = close  # type: ignore[method-assign]
    return wrapper


def _source_date(value: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%d-%b-%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"tanggal KSEI tidak valid: {value!r}") from exc


def normalize(path: Path) -> tuple[list[dict[str, str]], Counter[str]]:
    """Return normalized active common-share rows and exclusion counts."""
    with _open_master(path) as fh:
        # KSEI's text export occasionally wraps a description onto the next
        # physical line without CSV quoting.  Join such continuation lines so
        # their fields do not become a fake record with a broken Date value.
        physical_lines = fh.read().splitlines()
        logical_lines: list[str] = []
        for line in physical_lines:
            if line.startswith("Date|") or RECORD_START.match(line):
                logical_lines.append(line)
            elif logical_lines:
                logical_lines[-1] += " " + line
            else:
                raise ValueError("baris pertama master KSEI tidak valid")
        reader = csv.DictReader(io.StringIO("\n".join(logical_lines)), delimiter="|")
        headers = set(reader.fieldnames or [])
        missing = KSEI_REQUIRED - headers
        if missing:
            raise ValueError("kolom KSEI tidak ada: " + ", ".join(sorted(missing)))
        raw_rows = list(reader)

    source_dates = {_source_date(row["Date"]) for row in raw_rows if row.get("Date", "").strip()}
    if len(source_dates) != 1:
        raise ValueError("master KSEI harus memiliki satu source date")
    source_date = source_dates.pop()
    excluded: Counter[str] = Counter()
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in raw_rows:
        code = (row.get("Code") or "").strip().upper()
        if (row.get("Type") or "").strip().upper() != "EQUITY":
            excluded["non_equity"] += 1
            continue
        if (row.get("Status") or "").strip().upper() != "ACTIVE":
            excluded["inactive"] += 1
            continue
        if (row.get("Stock Exchange") or "").strip().upper() != "IDX":
            excluded["non_idx"] += 1
            continue
        if not CODE.fullmatch(code):
            excluded["invalid_code"] += 1
            continue
        name = (row.get("Description") or "").strip()
        sector = (row.get("Sector") or "").strip()
        if not name or not sector:
            excluded["missing_metadata"] += 1
            continue
        if code in seen:
            raise ValueError(f"kode saham duplikat: {code}")
        seen.add(code)
        result.append({
            "code": code,
            "name": name,
            "sector": sector,
            "board": "Unknown",
            "instrument_type": "stock",
            "status": "active",
            "source_date": source_date,
        })
    if not result:
        raise ValueError("tidak ada saham IDX aktif yang lolos filter KSEI")
    return sorted(result, key=lambda item: item["code"]), excluded


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="KSEI .txt atau .txt.zip")
    parser.add_argument("--output", type=Path, help="CSV UTF-8 hasil normalisasi")
    args = parser.parse_args()
    rows, excluded = normalize(args.file)
    output = args.output or args.file.with_name(f"idx-stocks-{rows[0]['source_date']}.csv")
    write_csv(rows, output)
    skipped = ", ".join(f"{key}={value}" for key, value in sorted(excluded.items())) or "0"
    print(f"dibuat: {output} ({len(rows)} saham; source date {rows[0]['source_date']})")
    print(f"dikecualikan: {skipped}; board=Unknown (tidak ada di master KSEI)")


if __name__ == "__main__":
    main()
