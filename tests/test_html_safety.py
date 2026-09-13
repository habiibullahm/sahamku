"""Semua teks yang dikirim dengan parse_mode HTML harus lolos parser Telegram:
tag yang diizinkan hanya b/i/u/s/code/pre/a; karakter < > & lain harus di-escape."""

import re

from sahamku.analysis.aftermarket import AfterMarketReport, TickerSignals
from sahamku.analysis.growth import GrowthCandidate
from sahamku.backtest.run import RuleResult, summary_text
from sahamku.report import format as fmt
from sahamku.signals.rules import RULE_LABELS

ALLOWED = re.compile(r"</?(b|i|u|s|code|pre|a)(\s[^<>]*)?>")


def assert_telegram_html(text: str) -> None:
    stripped = ALLOWED.sub("", text)
    assert "<" not in stripped and ">" not in stripped, stripped[:200]
    assert not re.search(r"&(?!amp;|lt;|gt;|quot;|#\d+;)", stripped), "ampersand tanpa escape"


def test_backtest_summary_escapes_labels():
    res = [RuleResult(rule, d, 10, {5: 50.0, 10: 55.0, 20: 60.0}, {5: 1.0, 10: 1.5, 20: 2.0},
                      {5: 1.0, 10: 1.5, 20: 2.0})
           for rule, d in (("death_cross", -1), ("golden_cross", 1))]
    assert_telegram_html(summary_text(res))


def test_aftermarket_escapes_labels():
    rules = [f"{RULE_LABELS[k]} (x)" for k in ("golden_cross", "death_cross")]
    r = AfterMarketReport(
        date="2026-09-11", ihsg_close=1.0, ihsg_pct=0.0, ihsg_volume=1.0, advancers=1,
        decliners=1, unchanged=0, gainers=[], losers=[],
        bullish=[TickerSignals("AAAA", 2, "bullish", rules)], bearish=[], squeeze=[], missing=[],
    )
    assert_telegram_html(fmt.aftermarket(r, cta=True, narrative="a < b & c"))


def test_stock_snapshot_escapes():
    text = fmt.stock_snapshot("BBCA", "2026-09-11", 1.0, 0.0, 1.0, {}, "bearish", -2,
                              [RULE_LABELS["death_cross"]], sr="S1 1 | R1 2")
    assert_telegram_html(text)


def test_growth_report_is_safe_and_within_telegram_limit():
    item = GrowthCandidate(
        "AAAA", 75, 15, 20, 18, 10, 12, 8.5, 20_000_000_000,
        ["tren <kuat>", "likuiditas & momentum"], ["drawdown >35%"],
    )
    text = fmt.growth_report("2026-09-11", [item] * 20, "universe liquid")
    assert len(text) <= fmt.TELEGRAM_MAX
    assert_telegram_html(text)
