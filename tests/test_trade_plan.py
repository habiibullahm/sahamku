from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from sahamku import db
from sahamku.analysis import trade_plan
from sahamku.report import format as fmt
from sahamku.universe import IHSG

TZ = ZoneInfo("Asia/Jakarta")


def _conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "trade-plan.db")
    db.init_db()
    return db.connect()


def _seed_market(conn):
    dates = pd.bdate_range("2025-10-01", periods=240)
    market_close = np.linspace(900, 1_100, len(dates))
    stock_close = np.linspace(900, 1_180, len(dates))
    stock_close[-1] = stock_close[-2] + 2
    market = pd.DataFrame({
        "open": market_close - 1, "high": market_close + 3, "low": market_close - 3,
        "close": market_close, "volume": np.full(len(dates), 1_000_000),
    }, index=dates)
    stock = pd.DataFrame({
        "open": stock_close - 2, "high": stock_close + 4, "low": stock_close - 4,
        "close": stock_close, "volume": np.full(len(dates), 5_000_000),
    }, index=dates)
    db.upsert_ohlcv(conn, IHSG, market)
    db.upsert_ohlcv(conn, "AAAA.JK", stock)
    day = dates[-1].strftime("%Y-%m-%d")
    db.replace_eligibility(conn, day, [
        ("AAAA.JK", 1, 240, 20, 60, 5_000_000_000, 5_000_000_000, ""),
    ])
    db.replace_growth_scores(conn, day, [
        ("AAAA.JK", 75, 15, 20, 18, 12, 10, 3, 5, 8,
         5_000_000_000, "[]", "[]"),
    ])
    db.trade_risk_set(conn, 7, 10_000_000, 1)
    conn.commit()
    return dates, stock


def test_risk_parser_and_price_ticks():
    assert trade_plan.parse_risk_args("10.000.000 1,5") == (10_000_000, 1.5)
    assert trade_plan.parse_risk_args("10.000.000") == (10_000_000, 1.0)
    assert trade_plan.tick_size(199) == 1
    assert trade_plan.tick_size(200) == 2
    assert trade_plan.tick_size(500) == 5
    assert trade_plan.tick_size(2_000) == 10
    assert trade_plan.tick_size(5_000) == 25
    assert trade_plan.round_price(1_252, 1_000, True) == 1_255
    assert trade_plan.round_price(1_252, 1_000, False) == 1_250


def test_create_plan_and_confirm_next_eod(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    dates, stock = _seed_market(conn)
    now = datetime.combine(dates[-1].date(), datetime.min.time(), TZ)
    plan = trade_plan.create(conn, 7, "AAAA", now=now)
    assert plan["status"] == "WAITING"
    assert plan["grade"] == "C"
    assert plan["target"] > plan["entry"] > plan["stop"]
    assert plan["lots"] >= 1

    next_day = dates[-1] + pd.offsets.BDay(1)
    breakout = float(plan["entry"] + trade_plan.tick_size(plan["entry"]))
    stock_row = pd.DataFrame({
        "open": [breakout], "high": [breakout + 5], "low": [breakout - 3],
        "close": [breakout], "volume": [10_000_000],
    }, index=[next_day])
    market_row = pd.DataFrame({
        "open": [1_101], "high": [1_108], "low": [1_100], "close": [1_107],
        "volume": [1_000_000],
    }, index=[next_day])
    db.upsert_ohlcv(conn, "AAAA.JK", stock_row)
    db.upsert_ohlcv(conn, IHSG, market_row)
    next_date = next_day.strftime("%Y-%m-%d")
    db.replace_eligibility(conn, next_date, [
        ("AAAA.JK", 1, 241, 20, 60, 5_000_000_000, 5_000_000_000, ""),
    ])
    conn.commit()
    events = trade_plan.evaluate_all(conn, now=now)
    assert [event.event for event in events] == ["confirmed"]
    saved = db.trade_plan_active_for(conn, 7, "AAAA.JK")
    assert saved["status"] == "CONFIRMED"


def test_catalyst_and_formatter_escape_html(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    dates, _ = _seed_market(conn)
    day = dates[-1].strftime("%Y-%m-%d")
    item = {
        "id": "news-1", "source": "Kontan", "title": "AAAA raih kontrak <besar>",
        "summary": "Ekspansi proyek baru", "link": "https://example.com/?a=1&b=2",
        "published": f"{day}T08:00:00+07:00",
    }
    assert db.news_insert(conn, item, "AAAA")
    db.news_set_analysis(conn, "news-1", "AAAA", 1, True)
    conn.commit()
    now = datetime.fromisoformat(f"{day}T12:00:00+07:00")
    catalyst = trade_plan.catalyst_for(conn, "AAAA", now)
    assert catalyst.grade == "B"
    assert catalyst.kind == "Kontrak/ekspansi"
    plan = trade_plan.create(conn, 7, "AAAA", now=now)
    text = fmt.trade_plan_report(plan)
    assert "&lt;besar&gt;" in text
    assert "Grade <b>B</b>" in text
    assert len(text) <= 4096
    HTMLParser().feed(text)


def test_sector_catalyst_requires_matching_positive_news(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    dates, _ = _seed_market(conn)
    day = dates[-1].strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO securities VALUES (?,?,?,?,?,?,?,?)",
        ("AAAA", "Alpha Energy", "Energy", "Main", "Stock", "Active", day, day),
    )
    item = {
        "id": "sector-1", "source": "CNBC", "title": "Harga batu bara menguat",
        "summary": "Sentimen positif untuk sektor energi", "link": "https://example.com/coal",
        "published": f"{day}T08:00:00+07:00",
    }
    assert db.news_insert(conn, item, "")
    db.news_set_analysis(conn, "sector-1", "", 1, True)
    conn.commit()
    catalyst = trade_plan.catalyst_for(
        conn, "AAAA", datetime.fromisoformat(f"{day}T12:00:00+07:00")
    )
    assert catalyst.grade == "B"
    assert catalyst.kind == "Katalis sektoral"
