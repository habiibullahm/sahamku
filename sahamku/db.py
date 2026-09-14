"""SQLite storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta

import pandas as pd

from sahamku.config import TZ, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS global_ohlcv (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS indicators (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    sma20 REAL, sma50 REAL, sma200 REAL, ema9 REAL, ema21 REAL,
    rsi14 REAL, macd REAL, macd_signal REAL, macd_hist REAL,
    bb_upper REAL, bb_mid REAL, bb_lower REAL, atr14 REAL, vol_avg20 REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS signals (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    rule   TEXT NOT NULL,
    direction INTEGER NOT NULL,
    detail TEXT,
    PRIMARY KEY (ticker, date, rule)
);
CREATE TABLE IF NOT EXISTS ratings (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    score  INTEGER NOT NULL,
    rating TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS watchlist (
    chat_id INTEGER NOT NULL,
    code    TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, code)
);
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    joined_at TEXT NOT NULL,
    subscribed INTEGER NOT NULL DEFAULT 1,
    plan TEXT NOT NULL DEFAULT 'free'
);
CREATE TABLE IF NOT EXISTS ask_log (
    chat_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, day)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    metric TEXT NOT NULL,          -- close | rsi
    op TEXT NOT NULL,              -- > | < | >= | <=
    value REAL NOT NULL,
    created_at TEXT NOT NULL,
    triggered_at TEXT
);
CREATE TABLE IF NOT EXISTS narratives (
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kind, date)
);
CREATE TABLE IF NOT EXISTS news (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    link TEXT NOT NULL,
    published TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    tickers TEXT NOT NULL DEFAULT '',
    sentiment INTEGER,
    market INTEGER,
    analyzed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published);
CREATE TABLE IF NOT EXISTS user_prefs (
    chat_id INTEGER PRIMARY KEY,
    premarket INTEGER NOT NULL DEFAULT 1,
    aftermarket INTEGER NOT NULL DEFAULT 1,
    weekly INTEGER NOT NULL DEFAULT 1,
    alerts INTEGER NOT NULL DEFAULT 1,
    midday INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ask_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ask_history ON ask_history(chat_id, id);
CREATE TABLE IF NOT EXISTS intraday (
    ticker TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    open REAL, high REAL, low REAL, last REAL, volume REAL, prev_close REAL
);
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS idx_disclosures (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    published TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    document_id TEXT,
    observed_at TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_disclosures_ticker_published
ON idx_disclosures(ticker, published DESC);
CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    last_attempt TEXT NOT NULL,
    last_success TEXT,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS eod_state (
    date TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    missing_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS securities (
    code TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT NOT NULL, board TEXT NOT NULL,
    instrument_type TEXT NOT NULL, status TEXT NOT NULL, source_date TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS universe_eligibility (
    date TEXT NOT NULL, ticker TEXT NOT NULL, eligible INTEGER NOT NULL,
    history_bars INTEGER NOT NULL, traded_20 INTEGER NOT NULL, traded_60 INTEGER NOT NULL,
    median_value_20 REAL, median_value_60 REAL, exclusion_reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (date, ticker)
);
CREATE TABLE IF NOT EXISTS growth_scores (
    date TEXT NOT NULL, ticker TEXT NOT NULL, total REAL NOT NULL, liquidity REAL NOT NULL,
    momentum REAL NOT NULL, trend REAL NOT NULL, breakout REAL NOT NULL,
    accumulation_risk REAL NOT NULL, rel_20 REAL, rel_60 REAL, rel_120 REAL,
    median_value_20 REAL, explanations TEXT NOT NULL DEFAULT '[]',
    risk_flags TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_growth_date_total ON growth_scores(date, total DESC);
CREATE TABLE IF NOT EXISTS trade_risk_profiles (
    chat_id INTEGER PRIMARY KEY,
    capital REAL NOT NULL,
    risk_pct REAL NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    status TEXT NOT NULL,
    grade TEXT NOT NULL,
    growth_score REAL NOT NULL,
    catalyst_type TEXT,
    catalyst_source TEXT,
    catalyst_title TEXT,
    catalyst_link TEXT,
    catalyst_published TEXT,
    catalyst_observed TEXT,
    catalyst_risk TEXT,
    risk_flags TEXT NOT NULL DEFAULT '[]',
    close REAL NOT NULL,
    sma50 REAL NOT NULL,
    sma50_slope_pct REAL NOT NULL,
    sma200 REAL NOT NULL,
    rsi14 REAL NOT NULL,
    rel20 REAL NOT NULL,
    rel60 REAL NOT NULL,
    atr14 REAL NOT NULL,
    prior_high REAL NOT NULL,
    swing_support REAL,
    volume_ratio REAL NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    risk_pct REAL NOT NULL,
    risk_amount REAL NOT NULL,
    lots INTEGER NOT NULL,
    position_value REAL NOT NULL,
    setup_sessions INTEGER NOT NULL DEFAULT 0,
    holding_sessions INTEGER NOT NULL DEFAULT 0,
    last_evaluated_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trade_plans_chat_status
ON trade_plans(chat_id, status, ticker);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_plans_one_active
ON trade_plans(chat_id, ticker) WHERE status IN ('WAITING','ATTENTION','CONFIRMED');
CREATE TABLE IF NOT EXISTS trade_plan_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    price REAL,
    detail TEXT NOT NULL DEFAULT '',
    UNIQUE(plan_id, event)
);
"""

INDICATOR_COLS = [
    "sma20", "sma50", "sma200", "ema9", "ema21", "rsi14", "macd", "macd_signal",
    "macd_hist", "bb_upper", "bb_mid", "bb_lower", "atr14", "vol_avg20",
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path_abs, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Tambah kolom baru pada tabel lama (CREATE TABLE IF NOT EXISTS tidak mengubah tabel ada)."""
    wanted = {
        "users": {"plan": "TEXT NOT NULL DEFAULT 'free'"},
        "user_prefs": {"midday": "INTEGER NOT NULL DEFAULT 1"},
        "trade_plans": {
            "risk_flags": "TEXT NOT NULL DEFAULT '[]'",
            "sma50_slope_pct": "REAL NOT NULL DEFAULT 0",
            "swing_support": "REAL",
            "catalyst_observed": "TEXT",
        },
    }
    for table, cols in wanted.items():
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- OHLCV ----------

def upsert_ohlcv(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame,
                 table: str = "ohlcv") -> int:
    """df index = date, kolom open/high/low/close/volume (lowercase)."""
    if df.empty:
        return 0
    rows = [
        (
            ticker,
            pd.Timestamp(idx).strftime("%Y-%m-%d"),
            _f(r["open"]), _f(r["high"]), _f(r["low"]), _f(r["close"]), _f(r["volume"]),
        )
        for idx, r in df.iterrows()
    ]
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} (ticker,date,open,high,low,close,volume) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def load_ohlcv(conn: sqlite3.Connection, ticker: str, limit: int | None = None,
               table: str = "ohlcv") -> pd.DataFrame:
    q = f"SELECT date,open,high,low,close,volume FROM {table} WHERE ticker=? ORDER BY date"
    df = pd.read_sql_query(q, conn, params=(ticker,), parse_dates=["date"], index_col="date")
    if limit:
        df = df.tail(limit)
    return df


def latest_date(conn: sqlite3.Connection, table: str = "ohlcv",
                ticker: str | None = None) -> str | None:
    if ticker:
        row = conn.execute(f"SELECT MAX(date) d FROM {table} WHERE ticker=?", (ticker,)).fetchone()
    else:
        row = conn.execute(f"SELECT MAX(date) d FROM {table}").fetchone()
    return row["d"] if row else None


def tickers_with_date(conn: sqlite3.Connection, date_str: str, table: str = "ohlcv") -> set[str]:
    rows = conn.execute(f"SELECT ticker FROM {table} WHERE date=?", (date_str,)).fetchall()
    return {r["ticker"] for r in rows}


def close_on(conn: sqlite3.Connection, date_str: str, table: str = "ohlcv") -> pd.DataFrame:
    """Semua ticker pada satu tanggal + close hari sebelumnya untuk hitung % change."""
    q = f"""
    SELECT t.ticker, t.close, t.volume, t.high, t.low,
           (SELECT close FROM {table} p WHERE p.ticker=t.ticker AND p.date<t.date
            ORDER BY p.date DESC LIMIT 1) AS prev_close
    FROM {table} t WHERE t.date=?
    """
    return pd.read_sql_query(q, conn, params=(date_str,), index_col="ticker")


def replace_eligibility(conn: sqlite3.Connection, date_str: str, rows: list[tuple]) -> None:
    conn.execute("DELETE FROM universe_eligibility WHERE date=?", (date_str,))
    conn.executemany(
        "INSERT INTO universe_eligibility (date,ticker,eligible,history_bars,traded_20,"
        "traded_60,median_value_20,median_value_60,exclusion_reason) VALUES (?,?,?,?,?,?,?,?,?)",
        [(date_str, *r) for r in rows],
    )


def eligible_tickers(conn: sqlite3.Connection, date_str: str) -> list[str]:
    return [r["ticker"] for r in conn.execute(
        "SELECT ticker FROM universe_eligibility WHERE date=? AND eligible=1 ORDER BY ticker",
        (date_str,),
    )]


def replace_growth_scores(conn: sqlite3.Connection, date_str: str, rows: list[tuple]) -> None:
    conn.execute("DELETE FROM growth_scores WHERE date=?", (date_str,))
    conn.executemany(
        "INSERT INTO growth_scores (date,ticker,total,liquidity,momentum,trend,breakout,"
        "accumulation_risk,rel_20,rel_60,rel_120,median_value_20,explanations,risk_flags) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(date_str, *r) for r in rows],
    )


def growth_rows(conn: sqlite3.Connection, date_str: str, limit: int = 20,
                min_score: float = 0) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM growth_scores WHERE date=? AND total>=? ORDER BY total DESC, ticker LIMIT ?",
        (date_str, min_score, limit),
    ).fetchall()


# ---------- indicators / signals / ratings ----------

def upsert_indicators(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ",".join(INDICATOR_COLS)
    ph = ",".join("?" * (len(INDICATOR_COLS) + 2))
    rows = [
        (ticker, pd.Timestamp(idx).strftime("%Y-%m-%d"), *[_f(r[c]) for c in INDICATOR_COLS])
        for idx, r in df.iterrows()
    ]
    conn.executemany(
        f"INSERT OR REPLACE INTO indicators (ticker,date,{cols}) VALUES ({ph})", rows)
    return len(rows)


def load_indicators(conn: sqlite3.Connection, ticker: str,
                    limit: int | None = None) -> pd.DataFrame:
    cols = ",".join(INDICATOR_COLS)
    df = pd.read_sql_query(
        f"SELECT date,{cols} FROM indicators WHERE ticker=? ORDER BY date",
        conn, params=(ticker,), parse_dates=["date"], index_col="date",
    )
    return df.tail(limit) if limit else df


def replace_signals(conn: sqlite3.Connection, ticker: str, date_str: str,
                    signals: Iterable[tuple[str, int, str]]) -> None:
    conn.execute("DELETE FROM signals WHERE ticker=? AND date=?", (ticker, date_str))
    conn.executemany(
        "INSERT INTO signals (ticker,date,rule,direction,detail) VALUES (?,?,?,?,?)",
        [(ticker, date_str, rule, d, detail) for rule, d, detail in signals],
    )


def upsert_rating(conn: sqlite3.Connection, ticker: str, date_str: str,
                  score: int, rating: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ratings (ticker,date,score,rating) VALUES (?,?,?,?)",
        (ticker, date_str, score, rating),
    )


def signals_on(conn: sqlite3.Connection, date_str: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT s.ticker, s.rule, s.direction, s.detail, r.score, r.rating "
        "FROM signals s JOIN ratings r ON r.ticker=s.ticker AND r.date=s.date "
        "WHERE s.date=? ORDER BY r.score DESC, s.ticker", (date_str,),
    ).fetchall()


def ratings_on(conn: sqlite3.Connection, date_str: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ticker, score, rating FROM ratings WHERE date=? ORDER BY score DESC, ticker",
        (date_str,),
    ).fetchall()


def rating_for(conn: sqlite3.Connection, ticker: str, date_str: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT score, rating FROM ratings WHERE ticker=? AND date=?", (ticker, date_str)
    ).fetchone()


def signals_for(conn: sqlite3.Connection, ticker: str, date_str: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT rule, direction, detail FROM signals WHERE ticker=? AND date=?",
        (ticker, date_str),
    ).fetchall()


# ---------- users / watchlist ----------

def upsert_user(conn: sqlite3.Connection, chat_id: int, username: str | None) -> None:
    conn.execute(
        "INSERT INTO users (chat_id, username, joined_at) VALUES (?,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username",
        (chat_id, username, _now()),
    )


def subscribed_chat_ids(conn: sqlite3.Connection) -> list[int]:
    return [r["chat_id"] for r in conn.execute("SELECT chat_id FROM users WHERE subscribed=1")]


def set_subscribed(conn: sqlite3.Connection, chat_id: int, on: bool) -> None:
    conn.execute("UPDATE users SET subscribed=? WHERE chat_id=?", (1 if on else 0, chat_id))


def is_subscribed(conn: sqlite3.Connection, chat_id: int) -> bool:
    row = conn.execute("SELECT subscribed FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    return bool(row and row["subscribed"])


# ---------- rate limit /ask ----------

def ask_count_today(conn: sqlite3.Connection, chat_id: int) -> int:
    row = conn.execute(
        "SELECT n FROM ask_log WHERE chat_id=? AND day=?", (chat_id, _today())).fetchone()
    return int(row["n"]) if row else 0


def ask_increment(conn: sqlite3.Connection, chat_id: int) -> int:
    conn.execute(
        "INSERT INTO ask_log (chat_id, day, n) VALUES (?,?,1) "
        "ON CONFLICT(chat_id, day) DO UPDATE SET n=n+1", (chat_id, _today()))
    return ask_count_today(conn, chat_id)


def watch_add(conn: sqlite3.Connection, chat_id: int, code: str) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO watchlist (chat_id, code, added_at) VALUES (?,?,?)",
        (chat_id, code.upper(), _now()),
    )
    return cur.rowcount > 0


def watch_remove(conn: sqlite3.Connection, chat_id: int, code: str) -> bool:
    cur = conn.execute(
        "DELETE FROM watchlist WHERE chat_id=? AND code=?", (chat_id, code.upper()))
    return cur.rowcount > 0


def watch_list(conn: sqlite3.Connection, chat_id: int) -> list[str]:
    return [r["code"] for r in conn.execute(
        "SELECT code FROM watchlist WHERE chat_id=? ORDER BY code", (chat_id,))]


# ---------- trade plans ----------

def trade_risk_set(conn: sqlite3.Connection, chat_id: int, capital: float,
                   risk_pct: float) -> None:
    conn.execute(
        "INSERT INTO trade_risk_profiles (chat_id,capital,risk_pct,updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET capital=excluded.capital, "
        "risk_pct=excluded.risk_pct, updated_at=excluded.updated_at",
        (chat_id, capital, risk_pct, _now()),
    )


def trade_risk_get(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT capital,risk_pct,updated_at FROM trade_risk_profiles WHERE chat_id=?",
        (chat_id,),
    ).fetchone()


def trade_risk_clear(conn: sqlite3.Connection, chat_id: int) -> bool:
    return conn.execute(
        "DELETE FROM trade_risk_profiles WHERE chat_id=?", (chat_id,)
    ).rowcount > 0


def trade_plan_active_for(conn: sqlite3.Connection, chat_id: int,
                          ticker: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM trade_plans WHERE chat_id=? AND ticker=? "
        "AND status IN ('WAITING','ATTENTION','CONFIRMED') ORDER BY id DESC LIMIT 1",
        (chat_id, ticker),
    ).fetchone()


def trade_plans_for(conn: sqlite3.Connection, chat_id: int,
                    active_only: bool = True) -> list[sqlite3.Row]:
    q = "SELECT * FROM trade_plans WHERE chat_id=?"
    if active_only:
        q += " AND status IN ('WAITING','ATTENTION','CONFIRMED')"
    return conn.execute(q + " ORDER BY id DESC", (chat_id,)).fetchall()


def trade_plans_active(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trade_plans WHERE status IN ('WAITING','ATTENTION','CONFIRMED') "
        "ORDER BY id"
    ).fetchall()


def trade_plan_add(conn: sqlite3.Connection, values: dict) -> int:
    cols = ",".join(values)
    placeholders = ",".join("?" for _ in values)
    cur = conn.execute(
        f"INSERT INTO trade_plans ({cols}) VALUES ({placeholders})",
        tuple(values.values()),
    )
    return int(cur.lastrowid)


def trade_plan_update(conn: sqlite3.Connection, plan_id: int, **values) -> None:
    if not values:
        return
    assignments = ",".join(f"{key}=?" for key in values)
    conn.execute(
        f"UPDATE trade_plans SET {assignments} WHERE id=?",
        (*values.values(), plan_id),
    )


def trade_plan_cancel(conn: sqlite3.Connection, chat_id: int, plan_id: int) -> bool:
    cur = conn.execute(
        "UPDATE trade_plans SET status='CANCELLED', closed_at=? "
        "WHERE id=? AND chat_id=? AND status IN ('WAITING','ATTENTION','CONFIRMED')",
        (_now(), plan_id, chat_id),
    )
    return cur.rowcount > 0


def trade_plan_event_add(conn: sqlite3.Connection, plan_id: int, event: str,
                         observed_at: str, price: float | None, detail: str = "") -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO trade_plan_events "
        "(plan_id,event,observed_at,price,detail) VALUES (?,?,?,?,?)",
        (plan_id, event, observed_at, price, detail),
    )
    return cur.rowcount > 0


def trade_confirmed_risk_pct(conn: sqlite3.Connection, chat_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(risk_pct),0) AS total FROM trade_plans "
        "WHERE chat_id=? AND status='CONFIRMED'", (chat_id,)
    ).fetchone()
    return float(row["total"])


# ---------- alerts ----------

def alert_add(conn: sqlite3.Connection, chat_id: int, code: str, metric: str, op: str,
              value: float) -> int:
    cur = conn.execute(
        "INSERT INTO alerts (chat_id, code, metric, op, value, created_at) VALUES (?,?,?,?,?,?)",
        (chat_id, code.upper(), metric, op, value, _now()))
    return cur.lastrowid


def alert_list(conn: sqlite3.Connection, chat_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, code, metric, op, value FROM alerts "
        "WHERE chat_id=? AND triggered_at IS NULL ORDER BY id", (chat_id,)).fetchall()


def alert_count(conn: sqlite3.Connection, chat_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE chat_id=? AND triggered_at IS NULL",
        (chat_id,)).fetchone()[0]


def alert_remove(conn: sqlite3.Connection, chat_id: int, alert_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM alerts WHERE id=? AND chat_id=? AND triggered_at IS NULL",
        (alert_id, chat_id))
    return cur.rowcount > 0


def alerts_active(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, chat_id, code, metric, op, value FROM alerts "
        "WHERE triggered_at IS NULL ORDER BY code").fetchall()


def alert_mark_triggered(conn: sqlite3.Connection, alert_id: int) -> None:
    conn.execute("UPDATE alerts SET triggered_at=? WHERE id=?", (_now(), alert_id))


# ---------- mingguan ----------

def trading_dates_between(conn: sqlite3.Connection, start: str, end: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT date FROM ohlcv WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end)).fetchall()
    return [r["date"] for r in rows]


def ratings_between(conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ticker, date, score, rating FROM ratings WHERE date BETWEEN ? AND ? "
        "AND rating != 'netral' ORDER BY date", (start, end)).fetchall()


def close_at(conn: sqlite3.Connection, ticker: str, date_str: str) -> float | None:
    row = conn.execute(
        "SELECT close FROM ohlcv WHERE ticker=? AND date=?", (ticker, date_str)).fetchone()
    return float(row["close"]) if row else None


# ---------- narasi ----------

def narrative_get(conn: sqlite3.Connection, kind: str, date_str: str) -> str | None:
    row = conn.execute(
        "SELECT text FROM narratives WHERE kind=? AND date=?", (kind, date_str)).fetchone()
    return row["text"] if row else None


def narrative_set(conn: sqlite3.Connection, kind: str, date_str: str, text: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO narratives (kind, date, text, created_at) VALUES (?,?,?,?)",
        (kind, date_str, text, _now()))


# ---------- news ----------

def eod_state_set(conn: sqlite3.Connection, date_str: str, status: str, attempt: int,
                  missing_count: int) -> None:
    conn.execute(
        "INSERT INTO eod_state (date,status,attempt,missing_count,updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET status=excluded.status,attempt=excluded.attempt, "
        "missing_count=excluded.missing_count,updated_at=excluded.updated_at",
        (date_str, status, attempt, missing_count, _now()),
    )


def eod_state_get(conn: sqlite3.Connection, date_str: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM eod_state WHERE date=?", (date_str,)).fetchone()

def idx_disclosure_upsert(conn: sqlite3.Connection, item: dict) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO idx_disclosures "
        "(id,ticker,published,category,title,url,document_id,observed_at,imported_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            item["id"], item["ticker"], item["published"], item["category"],
            item["title"], item["url"], item.get("document_id"),
            item["observed_at"], _now(),
        ),
    )
    return cur.rowcount > 0


def source_state_set(conn: sqlite3.Connection, source: str, status: str, detail: str = "",
                     success: bool = False) -> None:
    now = _now()
    conn.execute(
        "INSERT INTO source_state (source,last_attempt,last_success,status,detail) "
        "VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET "
        "last_attempt=excluded.last_attempt, "
        "last_success=CASE WHEN ? THEN excluded.last_success ELSE source_state.last_success END, "
        "status=excluded.status, detail=excluded.detail",
        (source, now, now if success else None, status, detail[:500], 1 if success else 0),
    )


def source_state_get(conn: sqlite3.Connection, source: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM source_state WHERE source=?", (source,)
    ).fetchone()


def news_insert(conn: sqlite3.Connection, it: dict, tickers: str) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO news (id, source, title, summary, link, published, fetched_at, "
        "tickers) VALUES (?,?,?,?,?,?,?,?)",
        (it["id"], it["source"], it["title"], it["summary"], it["link"], it["published"],
         _now(), tickers))
    return cur.rowcount > 0


def news_pending(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, source, title, summary, tickers FROM news WHERE analyzed_at IS NULL "
        "ORDER BY published DESC LIMIT ?", (limit,)).fetchall()


def news_set_analysis(conn: sqlite3.Connection, news_id: str, tickers: str, sentiment: int,
                      market: bool) -> None:
    conn.execute(
        "UPDATE news SET tickers=?, sentiment=?, market=?, analyzed_at=? WHERE id=?",
        (tickers, sentiment, 1 if market else 0, _now(), news_id))


def news_recent(conn: sqlite3.Connection, since_iso: str, code: str | None = None,
                limit: int = 20, market_only: bool = True) -> list[sqlite3.Row]:
    """Berita teranalisis sejak `since_iso`; jika `code`, hanya yang menyebut ticker itu."""
    q = ("SELECT source, title, link, published, tickers, sentiment FROM news "
         "WHERE analyzed_at IS NOT NULL AND published >= ?")
    args: list = [since_iso]
    if code:
        q += " AND (',' || tickers || ',') LIKE ?"
        args.append(f"%,{code.upper()},%")
    elif market_only:
        q += " AND market=1"
    q += " ORDER BY (tickers != '') DESC, published DESC LIMIT ?"
    args.append(limit)
    return conn.execute(q, args).fetchall()


def news_sentiment_by_ticker(conn: sqlite3.Connection, since_iso: str
                             ) -> dict[str, tuple[int, int]]:
    """{code: (jumlah positif, jumlah negatif)} untuk berita sejak since_iso."""
    out: dict[str, tuple[int, int]] = {}
    rows = conn.execute(
        "SELECT tickers, sentiment FROM news WHERE analyzed_at IS NOT NULL AND published >= ? "
        "AND tickers != ''", (since_iso,)).fetchall()
    for r in rows:
        for t in r["tickers"].split(","):
            if not t:
                continue
            pos, neg = out.get(t, (0, 0))
            if r["sentiment"] == 1:
                pos += 1
            elif r["sentiment"] == -1:
                neg += 1
            out[t] = (pos, neg)
    return out


# ---------- preferensi user ----------

PREF_KEYS = ("premarket", "aftermarket", "midday", "weekly", "alerts")


def prefs_get(conn: sqlite3.Connection, chat_id: int) -> dict[str, bool]:
    row = conn.execute("SELECT * FROM user_prefs WHERE chat_id=?", (chat_id,)).fetchone()
    return {k: bool(row[k]) if row else True for k in PREF_KEYS}


def prefs_toggle(conn: sqlite3.Connection, chat_id: int, key: str) -> bool:
    assert key in PREF_KEYS
    cur = prefs_get(conn, chat_id)
    new = not cur[key]
    conn.execute("INSERT OR IGNORE INTO user_prefs (chat_id) VALUES (?)", (chat_id,))
    conn.execute(f"UPDATE user_prefs SET {key}=? WHERE chat_id=?", (1 if new else 0, chat_id))
    return new


def recipients(conn: sqlite3.Connection, key: str) -> list[int]:
    """chat_id yang subscribed DAN mengaktifkan jenis laporan `key`."""
    assert key in PREF_KEYS
    return [r["chat_id"] for r in conn.execute(
        f"SELECT u.chat_id FROM users u LEFT JOIN user_prefs p ON p.chat_id=u.chat_id "
        f"WHERE u.subscribed=1 AND COALESCE(p.{key}, 1)=1")]


# ---------- memori /ask ----------

def ask_history_add(conn: sqlite3.Connection, chat_id: int, role: str, text: str) -> None:
    conn.execute("INSERT INTO ask_history (chat_id, role, text, ts) VALUES (?,?,?,?)",
                 (chat_id, role, text[:4000], _now()))


def ask_history_recent(conn: sqlite3.Connection, chat_id: int, limit: int = 6,
                       max_age_hours: int = 2) -> list[tuple[str, str]]:
    cutoff = (datetime.now(TZ) - timedelta(hours=max_age_hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT role, text FROM ask_history WHERE chat_id=? AND ts>=? ORDER BY id DESC LIMIT ?",
        (chat_id, cutoff, limit)).fetchall()
    return [(r["role"], r["text"]) for r in reversed(rows)]


def ask_history_clear(conn: sqlite3.Connection, chat_id: int) -> None:
    conn.execute("DELETE FROM ask_history WHERE chat_id=?", (chat_id,))


# ---------- admin stats ----------

def admin_stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    today = _today()
    return {
        "users": q("SELECT COUNT(*) FROM users"),
        "subscribed": q("SELECT COUNT(*) FROM users WHERE subscribed=1"),
        "with_watchlist": q("SELECT COUNT(DISTINCT chat_id) FROM watchlist"),
        "watch_rows": q("SELECT COUNT(*) FROM watchlist"),
        "alerts_active": q("SELECT COUNT(*) FROM alerts WHERE triggered_at IS NULL"),
        "ask_today": q("SELECT COALESCE(SUM(n),0) FROM ask_log WHERE day=?", today),
        "news_total": q("SELECT COUNT(*) FROM news"),
        "news_pending": q("SELECT COUNT(*) FROM news WHERE analyzed_at IS NULL"),
        "ohlcv_date": q("SELECT MAX(date) FROM ohlcv"),
        "tickers": q("SELECT COUNT(DISTINCT ticker) FROM ohlcv"),
    }


def job_runs_recent(conn: sqlite3.Connection, limit: int = 8) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT job, started_at, finished_at, status, detail FROM job_runs "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ---------- intraday ----------

def intraday_upsert(conn: sqlite3.Connection, ticker: str, date_str: str, ts: str, o: float,
                    h: float, lo: float, last: float, vol: float, prev: float | None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO intraday (ticker, date, ts, open, high, low, last, volume, "
        "prev_close) VALUES (?,?,?,?,?,?,?,?,?)", (ticker, date_str, ts, o, h, lo, last, vol, prev))


def intraday_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    today = _today()
    return conn.execute("SELECT * FROM intraday WHERE date=? ORDER BY ts DESC", (today,)).fetchall()


def intraday_get(conn: sqlite3.Connection, ticker: str,
                 date_str: str | None = None) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM intraday WHERE ticker=? AND date=?",
        (ticker, date_str or _today()),
    ).fetchone()


# ---------- plan (free/pro) ----------

def plan_get(conn: sqlite3.Connection, chat_id: int) -> str:
    row = conn.execute("SELECT plan FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    return row["plan"] if row else "free"


def plan_set(conn: sqlite3.Connection, chat_id: int, plan: str) -> bool:
    cur = conn.execute("UPDATE users SET plan=? WHERE chat_id=?", (plan, chat_id))
    return cur.rowcount > 0


def watch_count(conn: sqlite3.Connection, chat_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM watchlist WHERE chat_id=?", (chat_id,)).fetchone()[0]


# ---------- job runs ----------

def job_start(conn: sqlite3.Connection, job: str) -> int:
    cur = conn.execute(
        "INSERT INTO job_runs (job, started_at, status) VALUES (?,?,'running')", (job, _now()))
    return cur.lastrowid


def job_finish(conn: sqlite3.Connection, run_id: int, status: str, detail: str = "") -> None:
    conn.execute(
        "UPDATE job_runs SET finished_at=?, status=?, detail=? WHERE id=?",
        (_now(), status, detail[:2000], run_id),
    )


# ---------- helpers ----------

def _f(v) -> float | None:
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")
