"""Jalankan satu job secara manual (tanpa Telegram, output ke stdout).

Usage: python scripts/run_job.py eod|global|compute|premarket|aftermarket|chart [KODE]
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sahamku import db  # noqa: E402
from sahamku.analysis import aftermarket, premarket  # noqa: E402
from sahamku.ingestion.eod import ingest, validate_eod  # noqa: E402
from sahamku.ingestion.global_ import ingest_global  # noqa: E402
from sahamku.pipeline import load_joined, recompute_all  # noqa: E402
from sahamku.report import chart  # noqa: E402
from sahamku.report import format as fmt  # noqa: E402
from sahamku.universe import to_yf  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    job = sys.argv[1]
    db.init_db()
    with db.db() as conn:
        match job:
            case "eod":
                c = ingest(conn)
                ok, missing = validate_eod(conn, date.today())
                print(f"{len(c)} tickers; complete={ok}; missing={missing}")
            case "global":
                print(ingest_global(conn))
            case "compute":
                print("computed", recompute_all(conn))
            case "aftermarket":
                r = aftermarket.build(conn, watch_codes=["BBCA", "TLKM"])
                print(_strip(fmt.aftermarket(r)) if r else "no data")
            case "premarket":
                r = premarket.build(conn, watch_codes=["BBCA", "TLKM"])
                print(_strip(fmt.premarket(r)) if r else "no data")
            case "chart":
                code = (sys.argv[2] if len(sys.argv) > 2 else "BBCA").upper()
                print(chart.render(code, load_joined(conn, to_yf(code))))
            case _:
                print(__doc__)
                sys.exit(1)


def _strip(html: str) -> str:
    import re
    return re.sub(r"</?(b|i|code)>", "", html)


if __name__ == "__main__":
    main()
