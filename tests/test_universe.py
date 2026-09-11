from datetime import date

from sahamku.universe import from_yf, is_trading_day, to_yf


def test_ticker_conversion():
    assert to_yf("bbca") == "BBCA.JK"
    assert to_yf("^JKSE") == "^JKSE"
    assert from_yf("BBCA.JK") == "BBCA"


def test_trading_day():
    assert is_trading_day(date(2026, 9, 11))      # Jumat
    assert not is_trading_day(date(2026, 9, 12))  # Sabtu
    assert not is_trading_day(date(2026, 8, 17))  # libur nasional
