from sahamku.llm.ask import detect_codes


def test_detect_uppercase_and_dollar():
    assert detect_codes("kenapa BBCA dan $tlkm turun?") == ["BBCA", "TLKM"]


def test_lowercase_common_word_not_ticker():
    assert detect_codes("apa yang dilihat saat buka pasar besok?") == []


def test_dedupe_and_limit():
    assert detect_codes("BBCA BBCA BBRI BMRI TLKM") == ["BBCA", "BBRI", "BMRI"]


def test_embedded_letters_not_ticker():
    assert detect_codes("XBBCAX") == []
