"""Render candlestick chart PNG dengan mplfinance."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import mplfinance as mpf  # noqa: E402
import pandas as pd  # noqa: E402

from sahamku.config import settings  # noqa: E402


def render(code: str, joined: pd.DataFrame, bars: int = 60) -> Path:
    """joined: OHLCV + indikator. Return path PNG."""
    settings.charts_dir.mkdir(parents=True, exist_ok=True)
    df = joined.tail(bars).copy()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    add = []
    for col, color in (("sma20", "#1f77b4"), ("sma50", "#ff7f0e"), ("sma200", "#9467bd")):
        if col in df and df[col].notna().any():
            add.append(mpf.make_addplot(df[col], color=color, width=1.0))
    if "bb_upper" in df and df["bb_upper"].notna().any():
        add.append(mpf.make_addplot(df["bb_upper"], color="#aaaaaa", width=0.7, linestyle="--"))
        add.append(mpf.make_addplot(df["bb_lower"], color="#aaaaaa", width=0.7, linestyle="--"))
    if "rsi14" in df and df["rsi14"].notna().any():
        add.append(mpf.make_addplot(df["rsi14"], panel=2, color="#2ca02c", ylabel="RSI"))
        add.append(mpf.make_addplot(pd.Series(70, index=df.index), panel=2,
                                    color="#cccccc", width=0.6, secondary_y=False))
        add.append(mpf.make_addplot(pd.Series(30, index=df.index), panel=2,
                                    color="#cccccc", width=0.6, secondary_y=False))

    style = mpf.make_mpf_style(base_mpf_style="yahoo", gridstyle=":")
    out = settings.charts_dir / f"{code}_{df.index[-1].strftime('%Y%m%d')}.png"
    mpf.plot(
        df, type="candle", volume=True, addplot=add or None, style=style,
        title=f"{code} — {bars} hari", ylabel="Harga", ylabel_lower="Vol",
        panel_ratios=(3, 1, 1) if any(a.get("panel") == 2 for a in add) else (3, 1),
        figsize=(11, 8), savefig={"fname": str(out), "dpi": 110, "bbox_inches": "tight"},
    )
    return out
