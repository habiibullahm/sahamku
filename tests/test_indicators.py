import numpy as np

from sahamku.indicators.technical import compute, rsi


def test_compute_columns_and_warmup(ohlcv):
    ind = compute(ohlcv)
    for col in ["sma20", "sma50", "sma200", "rsi14", "macd", "bb_upper", "atr14", "vol_avg20"]:
        assert col in ind.columns
    assert ind["sma200"].iloc[:199].isna().all()
    assert ind["sma200"].iloc[199:].notna().all()
    assert np.isclose(ind["sma20"].iloc[-1], ohlcv["close"].iloc[-20:].mean())


def test_rsi_bounds(ohlcv):
    r = rsi(ohlcv["close"]).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_bb_ordering(ohlcv):
    ind = compute(ohlcv).dropna()
    assert (ind["bb_upper"] >= ind["bb_mid"]).all()
    assert (ind["bb_mid"] >= ind["bb_lower"]).all()
