"""SQLite storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime

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
    subscribed INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ask_log (
    chat_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, day)
);
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail TEXT
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
        conn.commit()
    finally:
        conn.close()


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
