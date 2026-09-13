"""Validate and import a normalized IDX securities CSV.

Usage: python scripts/update_universe.py FILE.csv [--apply] [--force]
Required columns: code,name,sector,board,instrument_type,status
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sahamku import db  # noqa: E402
from sahamku.config import TZ  # noqa: E402

REQUIRED = {"code", "name", "sector", "board", "instrument_type", "status"}
CODE = re.compile(r"^[A-Z]{4}$")
COMMON = {"stock", "common stock", "saham"}
STATUSES = {"active", "suspended", "delisted"}


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError("kolom wajib tidak ada: " + ", ".join(sorted(missing)))
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in reader]
    codes = [r["code"].upper() for r in rows]
    errors = []
    if len(codes) != len(set(codes)):
        errors.append("kode duplikat")
    for i, row in enumerate(rows, 2):
        row["code"] = row["code"].upper()
        row["instrument_type"] = row["instrument_type"].lower()
        row["status"] = row["status"].lower()
        if not CODE.fullmatch(row["code"]):
            errors.append(f"baris {i}: kode tidak valid")
        if not all(row[k] for k in REQUIRED):
            errors.append(f"baris {i}: field kosong")
        if row["instrument_type"] not in COMMON:
            errors.append(f"baris {i}: instrument_type tidak didukung")
        if row["status"] not in STATUSES:
            errors.append(f"baris {i}: status tidak didukung")
    if errors:
        raise ValueError("; ".join(errors[:20]))
    return rows


def import_rows(conn, rows: list[dict[str, str]], source_date: str,
                force: bool = False) -> int:
    date.fromisoformat(source_date)
    old = conn.execute("SELECT COUNT(*) FROM securities").fetchone()[0]
    if old and abs(len(rows) - old) / old > .35 and not force:
        raise ValueError(
            f"perubahan jumlah {old} -> {len(rows)} melebihi 35%; cek file atau gunakan --force"
        )
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn.execute("DELETE FROM securities")
    conn.executemany(
        "INSERT INTO securities (code,name,sector,board,instrument_type,status,source_date,"
        "imported_at) VALUES (?,?,?,?,?,?,?,?)",
        [(r["code"], r["name"], r["sector"], r["board"], r["instrument_type"],
          r["status"], r.get("source_date") or source_date, now) for r in rows],
    )
    # Scores and eligibility refer to the previous membership. Leaving them
    # behind would make reports look current while ranking a different master.
    conn.execute("DELETE FROM universe_eligibility")
    conn.execute("DELETE FROM growth_scores")
    conn.execute("DELETE FROM narratives")
    return old


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--apply", action="store_true", help="simpan setelah validasi")
    ap.add_argument("--force", action="store_true", help="izinkan perubahan jumlah >35%")
    ap.add_argument("--source-date", default=date.today().isoformat())
    args = ap.parse_args()
    rows = load(args.file)
    db.init_db()
    with db.db() as conn:
        old = conn.execute("SELECT COUNT(*) FROM securities").fetchone()[0]
        print(f"valid: {len(rows)} saham; sebelumnya {old}; apply={args.apply}")
        if not args.apply:
            return
        try:
            import_rows(conn, rows, args.source_date, args.force)
        except ValueError as exc:
            raise SystemExit(f"Ditolak: {exc}") from exc
    print("import selesai; restart bot untuk backfill ticker baru")


if __name__ == "__main__":
    main()
