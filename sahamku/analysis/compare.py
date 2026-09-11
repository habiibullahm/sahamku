"""/compare — bandingkan 2–4 saham: return 1W/1M/3M, RSI, posisi vs SMA, rating, chart."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from sahamku import db  # noqa: E402
from sahamku.config import settings  # noqa: E402
from sahamku.pipeline import load_joined  # noqa: E402
from sahamku.universe import to_yf  # noqa: E402

HORIZONS = {"1W": 5, "1M": 21, "3M": 63}
MAX_CODES = 4


@dataclass
class Row:
    code: str
    close: float
    ret: dict[str, float | None]
    rsi: float | None
    above_sma50: bool | None
    above_sma200: bool | None
    rating: str
    score: int


def build(conn: sqlite3.Connection, codes: list[str]) -> tuple[list[Row], dict[str, pd.Series]]:
    rows: list[Row] = []
    series: dict[str, pd.Series] = {}
    for code in codes[:MAX_CODES]:
        t = to_yf(code)
        j = load_joined(conn, t)
        if j.empty:
            continue
        last = j.iloc[-1]
        close = float(last["close"])
        ret = {}
        for k, n in HORIZONS.items():
            ret[k] = (close / float(j["close"].iloc[-n - 1]) - 1) * 100 if len(j) > n else None
        date_str = j.index[-1].strftime("%Y-%m-%d")
        rating = db.rating_for(conn, t, date_str)
        rows.append(Row(
            code=code, close=close, ret=ret,
            rsi=None if pd.isna(last["rsi14"]) else float(last["rsi14"]),
            above_sma50=None if pd.isna(last["sma50"]) else bool(close > last["sma50"]),
            above_sma200=None if pd.isna(last["sma200"]) else bool(close > last["sma200"]),
            rating=rating["rating"] if rating else "netral",
            score=int(rating["score"]) if rating else 0,
        ))
        tail = j["close"].tail(HORIZONS["3M"] + 1)
        series[code] = (tail / float(tail.iloc[0]) - 1) * 100
    return rows, series


def render_chart(series: dict[str, pd.Series]) -> Path:
    settings.charts_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for code, s in series.items():
        ax.plot(s.index, s.values, label=f"{code} ({s.iloc[-1]:+.1f}%)", linewidth=1.6)
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.set_title("Perbandingan return 3 bulan (normalisasi)")
    ax.set_ylabel("%")
    ax.grid(True, linestyle=":", linewidth=0.6)
    ax.legend()
    fig.autofmt_xdate()
    out = settings.charts_dir / f"compare_{'_'.join(series)}.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out
