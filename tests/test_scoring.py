from sahamku.signals.rules import Signal
from sahamku.signals.scoring import rating, score, score_and_rate


def test_score_weights():
    sigs = [Signal("golden_cross", 1, ""), Signal("rsi_overbought", -1, "")]
    assert score(sigs) == 1


def test_rating_thresholds():
    assert rating(2) == "bullish"
    assert rating(-2) == "bearish"
    assert rating(0) == "netral"


def test_neutral_signal_not_counted():
    sc, rt = score_and_rate([Signal("bb_squeeze", 0, "")])
    assert sc == 0 and rt == "netral"
