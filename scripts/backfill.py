"""Tarik histori awal: 3 tahun LQ45+IHSG, 1 tahun aset global, lalu hitung indikator & sinyal.

Usage: python scripts/backfill.py [--period 3y] [--skip-global]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sahamku import db  # noqa: E402
from sahamku.ingestion.eod import backfill  # noqa: E402
from sahamku.ingestion.global_ import backfill_global  # noqa: E402
from sahamku.pipeline import recompute_all  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="3y")
    ap.add_argument("--skip-global", action="store_true")
    args = ap.parse_args()

    db.init_db()
    with db.db() as conn:
        counts = backfill(conn, period=args.period)
        print(f"OHLCV: {len(counts)} tickers, {sum(counts.values())} rows")
        if not args.skip_global:
            g = backfill_global(conn)
            print(f"Global: {len(g)} tickers, {sum(g.values())} rows")
        n = recompute_all(conn)
        print(f"Indicators+signals computed for {n} tickers")


if __name__ == "__main__":
    main()
