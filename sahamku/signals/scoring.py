"""Gabungkan sinyal menjadi skor & rating."""

from __future__ import annotations

from sahamku.config import settings
from sahamku.signals.rules import Signal

# Bobot per rule: event (cross/breakout) lebih berarti daripada state (above/below SMA200)
RULE_WEIGHTS = {
    "golden_cross": 2, "death_cross": 2,
    "rsi_oversold": 1, "rsi_overbought": 1,
    "breakout_high": 2, "breakdown_low": 2,
    "macd_bull_cross": 1, "macd_bear_cross": 1,
    "bb_squeeze": 0,
    "above_sma200": 1, "below_sma200": 1,
}

RATING_EMOJI = {"bullish": "🟢", "bearish": "🔴", "netral": "⚪"}


def score(signals: list[Signal]) -> int:
    return sum(RULE_WEIGHTS.get(s.rule, 1) * s.direction for s in signals)


def rating(sc: int) -> str:
    if sc >= settings.signal_bullish_threshold:
        return "bullish"
    if sc <= settings.signal_bearish_threshold:
        return "bearish"
    return "netral"


def score_and_rate(signals: list[Signal]) -> tuple[int, str]:
    sc = score(signals)
    return sc, rating(sc)
