"""Validate and import an official IDX disclosure CSV, XLSX, or JSON export.

Usage: python scripts/import_idx_disclosures.py FILE [--apply]
Required columns: ticker, published, category, title, url
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sahamku import db  # noqa: E402
from sahamku.news import idx_disclosures  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--apply", action="store_true", help="simpan setelah validasi")
    args = parser.parse_args()

    records = idx_disclosures.load_file(args.file)
    db.init_db()
    with db.db() as conn:
        normalized = idx_disclosures.normalize(records, conn)
        print(f"valid: {len(normalized)} disclosure resmi; apply={args.apply}")
        if not args.apply:
            return
        imported = idx_disclosures.ingest_records(conn, records)
    print(f"import selesai: {imported} disclosure baru; analisis pada job berita berikutnya")


if __name__ == "__main__":
    main()
