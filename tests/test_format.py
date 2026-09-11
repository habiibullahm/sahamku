from sahamku.analysis.aftermarket import AfterMarketReport, Mover, TickerSignals
from sahamku.analysis.premarket import PreMarketReport
from sahamku.config import DISCLAIMER
from sahamku.report import format as fmt


def test_aftermarket_contains_sections():
    r = AfterMarketReport(
        date="2026-09-11", ihsg_close=6500.0, ihsg_pct=-1.2, ihsg_volume=1e9,
        advancers=10, decliners=30, unchanged=5,
        gainers=[Mover("BBCA", 6300, 1.5, 1e6)], losers=[Mover("TLKM", 2600, -2.0, 2e6)],
        bullish=[TickerSignals("BBRI", 3, "bullish", ["Golden cross <x>"])],
        bearish=[], squeeze=["INDF"], missing=["MAPA"],
        watchlist={"BBCA": (Mover("BBCA", 6300, 1.5, 1e6), None)},
    )
    out = fmt.aftermarket(r)
    assert "After Market 2026-09-11" in out
    assert "BBCA" in out and "TLKM" in out and "INDF" in out
    assert "&lt;x&gt;" in out  # HTML di-escape
    assert "MAPA" in out and DISCLAIMER in out
    assert len(out) <= fmt.TELEGRAM_MAX


def test_premarket_renders():
    r = PreMarketReport(
        date="2026-09-12", sentiment_score=-4, sentiment_label="BEARISH",
        global_rows=[("S&P 500", 7500.0, -0.5), ("Emas", None, None)],
        ihsg_close=6500.0, ihsg_pct=-1.0, ihsg_rsi=45.0, ihsg_trend="turun",
        support=6300.0, resistance=6700.0, notes=["catatan"], watchlist={"BBCA": "close 6,300"},
    )
    out = fmt.premarket(r)
    assert "BEARISH" in out and "S&amp;P 500" in out and "n/a" in out and "catatan" in out


def test_pct_and_vol():
    assert fmt.pct(1.234) == "▲ +1.23%"
    assert fmt.pct(None) == "n/a"
    assert fmt.vol(2_500_000) == "2.5jt"
    assert fmt.vol(1_200_000_000) == "1.20M"
