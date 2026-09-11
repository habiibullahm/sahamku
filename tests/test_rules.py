import pandas as pd

from sahamku.indicators.technical import compute
from sahamku.signals.rules import RULE_DIRECTION, evaluate_all, evaluate_latest


def test_evaluate_all_shape(ohlcv):
    joined = ohlcv.join(compute(ohlcv))
    flags = evaluate_all(joined)
    assert set(flags.columns) == set(RULE_DIRECTION)
    assert flags.dtypes.eq(bool).all()
    assert len(flags) == len(ohlcv)


def test_breakout_detected(ohlcv):
    df = ohlcv.copy()
    # Paksa bar terakhir: close di atas high 20D dengan volume 3x
    df.loc[df.index[-1], "close"] = df["high"].iloc[-21:-1].max() * 1.05
    df.loc[df.index[-1], "high"] = df.loc[df.index[-1], "close"] + 1
    df.loc[df.index[-1], "volume"] = df["volume"].iloc[-21:-1].mean() * 3
    joined = df.join(compute(df))
    rules = {s.rule for s in evaluate_latest(joined)}
    assert "breakout_high" in rules


def test_rsi_oversold_cross(ohlcv):
    df = ohlcv.copy()
    # Jatuhkan harga 15 hari terakhir supaya RSI turun tajam
    tail = df.index[-15:]
    df.loc[tail, "close"] = df["close"].iloc[-16] * (1 - 0.03 * pd.RangeIndex(1, 16))
    df.loc[tail, "low"] = df.loc[tail, "close"] - 1
    df.loc[tail, "high"] = df.loc[tail, "close"] + 1
    joined = df.join(compute(df))
    assert joined["rsi14"].iloc[-1] < 30
