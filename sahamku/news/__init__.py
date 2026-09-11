"""Berita & sentimen: ingest RSS + klasifikasi LLM."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from sahamku import db
from sahamku.config import TZ

SENT_EMOJI = {1: "🟢", -1: "🔴", 0: "⚪"}


@dataclass
class Headline:
    source: str
    title: str
    link: str
    tickers: list[str]
    sentiment: int


def since_iso(hours: int) -> str:
    return (datetime.now(TZ) - timedelta(hours=hours)).isoformat(timespec="minutes")


def headlines(conn: sqlite3.Connection, hours: int = 20, code: str | None = None,
              limit: int = 6) -> list[Headline]:
    rows = db.news_recent(conn, since_iso(hours), code=code, limit=limit)
    return [Headline(r["source"], r["title"], r["link"],
                     [t for t in (r["tickers"] or "").split(",") if t],
                     r["sentiment"] if r["sentiment"] is not None else 0) for r in rows]


def ticker_sentiment(conn: sqlite3.Connection, hours: int = 20) -> dict[str, tuple[int, int]]:
    return db.news_sentiment_by_ticker(conn, since_iso(hours))
