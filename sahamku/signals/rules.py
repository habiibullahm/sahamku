"""Rule-based signal engine. Setiap rule menerima OHLCV + indikator (sudah di-join)
dan mengembalikan list Signal untuk bar TERAKHIR (atau untuk semua bar via evaluate_all)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sahamku.config import settings

BULL, BEAR = 1, -1


@dataclass(frozen=True)
class Signal:
    rule: str
    direction: int  # +1 / -1
    detail: str


# Nama rule -> deskripsi manusiawi (dipakai di laporan & backtest)
RULE_LABELS = {
    "golden_cross": "Golden cross SMA50>SMA200",
    "death_cross": "Death cross SMA50<SMA200",
    "rsi_oversold": "RSI oversold",
    "rsi_overbought": "RSI overbought",
    "breakout_high": "Breakout high 20D + volume",
    "breakdown_low": "Breakdown low 20D + volume",
    "macd_bull_cross": "MACD cross up",
    "macd_bear_cross": "MACD cross down",
    "bb_squeeze": "Bollinger squeeze (siap breakout)",
    "above_sma200": "Harga di atas SMA200 (tren naik)",
    "below_sma200": "Harga di bawah SMA200 (tren turun)",
}


def evaluate_all(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized: return DataFrame boolean per rule per bar (untuk backtest)."""
    c = df["close"]
    out = pd.DataFrame(index=df.index)

    s50, s200 = df["sma50"], df["sma200"]
    out["golden_cross"] = (s50 > s200) & (s50.shift(1) <= s200.shift(1))
    out["death_cross"] = (s50 < s200) & (s50.shift(1) >= s200.shift(1))

    r = df["rsi14"]
    out["rsi_oversold"] = (r < settings.rsi_oversold) & (r.shift(1) >= settings.rsi_oversold)
    out["rsi_overbought"] = (r > settings.rsi_overbought) & (r.shift(1) <= settings.rsi_overbought)

    n = settings.breakout_lookback
    hi_n = df["high"].shift(1).rolling(n).max()
    lo_n = df["low"].shift(1).rolling(n).min()
    vol_ok = df["volume"] > settings.breakout_volume_mult * df["vol_avg20"]
    out["breakout_high"] = (c > hi_n) & vol_ok
    out["breakdown_low"] = (c < lo_n) & vol_ok

    m, ms = df["macd"], df["macd_signal"]
    out["macd_bull_cross"] = (m > ms) & (m.shift(1) <= ms.shift(1))
    out["macd_bear_cross"] = (m < ms) & (m.shift(1) >= ms.shift(1))

    width = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    out["bb_squeeze"] = width < settings.bb_squeeze_pct

    out["above_sma200"] = c > s200
    out["below_sma200"] = c < s200
    return out.fillna(False).astype(bool)


RULE_DIRECTION = {
    "golden_cross": BULL, "death_cross": BEAR,
    "rsi_oversold": BULL, "rsi_overbought": BEAR,
    "breakout_high": BULL, "breakdown_low": BEAR,
    "macd_bull_cross": BULL, "macd_bear_cross": BEAR,
    "bb_squeeze": 0,  # netral: hanya informasi
    "above_sma200": BULL, "below_sma200": BEAR,
}


def evaluate_latest(df: pd.DataFrame) -> list[Signal]:
    """Sinyal untuk bar terakhir, dengan detail angka."""
    if len(df) < 2:
        return []
    flags = evaluate_all(df).iloc[-1]
    last = df.iloc[-1]
    out: list[Signal] = []
    for rule, hit in flags.items():
        if not hit:
            continue
        out.append(Signal(rule, RULE_DIRECTION[rule], _detail(rule, last)))
    return out


def _detail(rule: str, row: pd.Series) -> str:
    match rule:
        case "rsi_oversold" | "rsi_overbought":
            return f"RSI {row['rsi14']:.1f}"
        case "breakout_high" | "breakdown_low":
            mult = row["volume"] / row["vol_avg20"] if row["vol_avg20"] else 0
            return f"vol {mult:.1f}x rata-rata"
        case "golden_cross" | "death_cross" | "above_sma200" | "below_sma200":
            return f"SMA50 {row['sma50']:.0f} / SMA200 {row['sma200']:.0f}"
        case "macd_bull_cross" | "macd_bear_cross":
            return f"MACD {row['macd']:.1f} vs sig {row['macd_signal']:.1f}"
        case "bb_squeeze":
            w = (row["bb_upper"] - row["bb_lower"]) / row["bb_mid"] * 100
            return f"lebar BB {w:.1f}%"
    return ""
