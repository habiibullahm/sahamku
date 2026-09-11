"""Ambil berita dari RSS, simpan ke tabel news (dedupe by link)."""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from calendar import timegm
from datetime import UTC, datetime

import feedparser

from sahamku import db
from sahamku.config import TZ
from sahamku.universe import LQ45, NAME_ALIASES

log = logging.getLogger(__name__)

FEEDS: dict[str, str] = {
    "CNBC": "https://www.cnbcindonesia.com/market/rss",
    "Kontan": "https://investasi.kontan.co.id/rss",
    "IDX Channel": "https://www.idxchannel.com/rss/market-news",
    "Liputan6": "https://feed.liputan6.com/rss/saham",
    "Detik": "https://finance.detik.com/rss",
}
UA = {"User-Agent": "Mozilla/5.0 (compatible; SahamkuBot/1.0)"}
_TAG = re.compile(r"<[^>]+>")
_CODE = re.compile(r"\b([A-Z]{4})\b")


def _clean(s: str, limit: int = 300) -> str:
    s = _TAG.sub(" ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _published(e) -> str:
    st = e.get("published_parsed") or e.get("updated_parsed")
    if st:
        dt = datetime.fromtimestamp(timegm(st), tz=UTC).astimezone(TZ)
        return dt.isoformat(timespec="minutes")
    return datetime.now(TZ).isoformat(timespec="minutes")


def rule_tickers(text: str) -> list[str]:
    """Deteksi ticker cepat tanpa LLM: kode kapital atau alias nama perusahaan."""
    found: list[str] = []
    for m in _CODE.finditer(text):
        c = m.group(1)
        if c in LQ45 and c not in found:
            found.append(c)
    low = text.lower()
    for code, aliases in NAME_ALIASES.items():
        if code in found:
            continue
        if any(re.search(rf"\b{re.escape(a.lower())}\b", low) for a in aliases):
            found.append(code)
    return found[:4]


def fetch_all() -> list[dict]:
    items: list[dict] = []
    for source, url in FEEDS.items():
        try:
            f = feedparser.parse(url, request_headers=UA)
        except Exception:
            log.warning("feed %s gagal", source, exc_info=True)
            continue
        for e in f.entries:
            link = e.get("link") or ""
            title = _clean(e.get("title", ""), 200)
            if not link or not title:
                continue
            items.append({
                "id": hashlib.sha1(link.encode()).hexdigest()[:16],
                "source": source,
                "title": title,
                "summary": _clean(e.get("summary", "") or e.get("description", "")),
                "link": link,
                "published": _published(e),
            })
        log.info("feed %s: %d item", source, len(f.entries))
    return items


def ingest(conn: sqlite3.Connection) -> int:
    """Simpan item baru. Return jumlah baris baru."""
    new = 0
    for it in fetch_all():
        tick = rule_tickers(f"{it['title']} {it['summary']}")
        if db.news_insert(conn, it, ",".join(tick)):
            new += 1
    conn.commit()
    log.info("news: %d baru", new)
    return new
