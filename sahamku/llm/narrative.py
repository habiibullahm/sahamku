"""Narasi AI singkat untuk laporan: dibuat sekali per (jenis, tanggal), disimpan di DB,
dipakai ulang untuk semua user & channel supaya konsisten dan hemat kuota."""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3

from sahamku import db
from sahamku.config import settings
from sahamku.llm.providers import generate

log = logging.getLogger(__name__)

SYSTEM = """Kamu analis teknikal pasar saham Indonesia; tulis ringkasan untuk investor ritel.
Tulis 2–3 kalimat dalam Bahasa Indonesia yang menjelaskan "apa artinya" data laporan berikut:
kondisi pasar hari ini, faktor yang menonjol, dan hal yang perlu diperhatikan sesi berikutnya.
Aturan: gunakan hanya angka yang ada di data; tanpa bullet, tanpa heading, tanpa emoji;
jangan memberi perintah beli/jual; jangan menulis disclaimer (sudah ada di laporan);
sebut paling banyak 3–4 saham; maksimal 60 kata."""

TIMEOUT_S = 25
_TAG = re.compile(r"<[^>]+>")


def _plain(html: str) -> str:
    text = _TAG.sub("", html).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # buang disclaimer & CTA supaya model fokus ke data
    lines = [ln for ln in text.splitlines()
             if "Bukan saran investasi" not in ln and "tanya AI" not in ln]
    return "\n".join(lines).strip()


async def get_or_create(conn: sqlite3.Connection, kind: str, date_str: str,
                        report_html: str) -> str | None:
    """Return narasi (cache DB) atau None bila LLM nonaktif/gagal."""
    if not settings.narrative_enabled:
        return None
    cached = db.narrative_get(conn, kind, date_str)
    if cached:
        return cached
    prompt = f"Jenis laporan: {kind}\nData:\n{_plain(report_html)}"
    try:
        res = await asyncio.wait_for(generate(SYSTEM, prompt), TIMEOUT_S)
    except Exception:
        log.warning("narasi %s %s gagal", kind, date_str, exc_info=True)
        return None
    if res.error or not res.text:
        log.warning("narasi %s %s: %s", kind, date_str, res.error or "kosong")
        return None
    text = " ".join(res.text.replace("**", "").split())
    db.narrative_set(conn, kind, date_str, text)
    conn.commit()
    return text
