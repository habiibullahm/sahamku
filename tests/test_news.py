from sahamku.news import ingest, sentiment


def test_rule_tickers_code_and_alias():
    assert ingest.rule_tickers("Saham BBCA naik, Telkom Indonesia stagnan") == ["BBCA", "TLKM"]
    assert set(ingest.rule_tickers("Bank Mandiri dan BRI catat laba")) == {"BMRI", "BBRI"}
    assert ingest.rule_tickers("Harga cabai naik di pasar") == []


def test_parse_clean_and_truncated_json():
    ok = ('[{"i":0,"tickers":["BBCA"],"sentiment":1,"market":true},'
          '{"i":1,"tickers":[],"sentiment":0,"market":false}]')
    assert [d["i"] for d in sentiment._parse(ok)] == [0, 1]
    cut = '[{"i":0,"tickers":["BBCA"],"sentiment":1,"market":true},{"i":1,"tick'
    assert [d["i"] for d in sentiment._parse(cut)] == [0]
    assert sentiment._parse("tidak ada json") == []
