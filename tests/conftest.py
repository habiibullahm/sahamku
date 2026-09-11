import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    """300 bar sintetis: tren naik dengan noise deterministik."""
    rng = np.random.default_rng(42)
    n = 300
    idx = pd.bdate_range("2025-01-01", periods=n)
    close = 1000 + np.cumsum(rng.normal(1.0, 8.0, n))
    close = np.maximum(close, 100)
    high = close + rng.uniform(0, 10, n)
    low = close - rng.uniform(0, 10, n)
    open_ = close + rng.normal(0, 3, n)
    vol = rng.uniform(1e6, 3e6, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)
