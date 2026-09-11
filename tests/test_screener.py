from sahamku import screener


def test_parse_combo():
    q = screener.parse("rating=bullish rsi<35 vol>2x above200 chg>=1.5")
    assert q.rating == "bullish"
    assert ("rsi", "<", 35.0) in q.cmp and ("vol", ">", 2.0) in q.cmp
    assert ("chg", ">=", 1.5) in q.cmp
    assert q.flags == ["above_sma200"] and not q.errors and not q.empty


def test_parse_errors_and_empty():
    q = screener.parse("foo rsi<<3")
    assert q.errors == ["foo", "rsi<<3"]
    assert screener.parse("").empty


def test_describe_roundtrip():
    q = screener.parse("rsi<30 squeeze vol>1.5x")
    assert screener.describe(q) == "rsi<30 vol>1.5x squeeze"
