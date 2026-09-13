"""Backtest sederhana: untuk setiap rule, return forward 5/10/20 hari setelah sinyal.

Usage: python -m sahamku.backtest.run [--years 3]
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from dataclasses import dataclass
from html import escape

import pandas as pd

from sahamku import db
from sahamku.indicators.technical import compute
from sahamku.signals.rules import RULE_DIRECTION, RULE_LABELS, evaluate_all
from sahamku.universe import active_tickers

log = logging.getLogger(__name__)
HORIZONS = (5, 10, 20)


@dataclass
class RuleResult:
    rule: str
    direction: int
    n: int
    win_rate: dict[int, float]      # horizon -> % sinyal yang searah (bullish: return>0)
    avg_return: dict[int, float]    # horizon -> rata-rata return % (searah sinyal)
    median_return: dict[int, float]


def run_backtest(conn: sqlite3.Connection, tickers: list[str] | None = None,
                 years: int = 3) -> list[RuleResult]:
    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    events: dict[str, list[pd.Series]] = {r: [] for r in RULE_DIRECTION}

    for t in tickers or active_tickers(conn):
        ohlcv = db.load_ohlcv(conn, t)
        if len(ohlcv) < 250:
            continue
        joined = ohlcv.join(compute(ohlcv))
        flags = evaluate_all(joined)
        close = joined["close"]
        fwd = {h: (close.shift(-h) / close - 1) * 100 for h in HORIZONS}
        for rule, direction in RULE_DIRECTION.items():
            if direction == 0:
                continue
            hits = flags.index[flags[rule] & (flags.index >= cutoff)]
            for d in hits:
                row = {h: fwd[h].get(d) for h in HORIZONS}
                if any(pd.isna(v) for v in row.values()):
                    continue
                events[rule].append(pd.Series(row))

    results: list[RuleResult] = []
    for rule, direction in RULE_DIRECTION.items():
        if direction == 0 or not events[rule]:
            continue
        df = pd.DataFrame(events[rule]) * direction  # searah sinyal → positif = benar
        results.append(RuleResult(
            rule=rule, direction=direction, n=len(df),
            win_rate={h: float((df[h] > 0).mean() * 100) for h in HORIZONS},
            avg_return={h: float(df[h].mean()) for h in HORIZONS},
            median_return={h: float(df[h].median()) for h in HORIZONS},
        ))
    results.sort(key=lambda r: -r.win_rate[10])
    return results


def summary_text(results: list[RuleResult], universe: str = "universe aktif") -> str:
    lines = [f"🧪 <b>Backtest rule ({escape(universe)}, 3 tahun)</b>",
             "rule · n · win% (5/10/20D) · avg ret% (10D)"]
    for r in results:
        lines.append(
            f"• {escape(RULE_LABELS.get(r.rule, r.rule))} · n={r.n} · "
            f"{r.win_rate[5]:.0f}/{r.win_rate[10]:.0f}/{r.win_rate[20]:.0f}% · "
            f"{r.avg_return[10]:+.2f}%"
        )
    lines.append("\n<i>Return dihitung searah sinyal (bearish: return negatif = benar). "
                 "Belum termasuk biaya transaksi.</i>")
    return "\n".join(lines)


def summary_markdown(results: list[RuleResult]) -> str:
    head = "| Rule | Arah | n | Win 5D | Win 10D | Win 20D | Avg 5D | Avg 10D | Avg 20D |"
    sep = "|---|---|---|---|---|---|---|---|---|"
    rows = [head, sep]
    for r in results:
        rows.append(
            f"| {RULE_LABELS.get(r.rule, r.rule)} | {'bull' if r.direction > 0 else 'bear'} | "
            f"{r.n} | {r.win_rate[5]:.1f}% | {r.win_rate[10]:.1f}% | {r.win_rate[20]:.1f}% | "
            f"{r.avg_return[5]:+.2f}% | {r.avg_return[10]:+.2f}% | {r.avg_return[20]:+.2f}% |"
        )
    return "\n".join(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=3)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    with db.db() as conn:
        res = run_backtest(conn, years=args.years)
    print(summary_markdown(res))
