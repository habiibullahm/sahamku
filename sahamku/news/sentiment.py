"""Klasifikasi sentimen & ticker berita via LLM (batch, output JSON)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3

from sahamku import db
from sahamku.llm.providers import generate
from sahamku.universe import NAME_ALIASES, STOCKS

log = logging.getLogger(__name__)

BATCH = 15
TIMEOUT_S = 45

SYSTEM = """Kamu analis berita pasar modal Indonesia. Untuk setiap berita, tentukan:
- "tickers": daftar kode saham LQ45 yang benar-benar menjadi subjek berita (bukan sekadar disebut),
  hanya dari daftar berikut: {codes}. Kosongkan [] jika tidak ada.
- "sentiment": dampak untuk harga saham terkait (atau pasar/IHSG jika tanpa ticker):
  1 positif, -1 negatif, 0 netral/tidak relevan.
- "market": true jika berita relevan untuk pasar saham Indonesia secara umum (IHSG, makro, sektor),
  false jika tidak relevan (olahraga, gaya hidup, dll).
Alias nama perusahaan: {aliases}
Jawab HANYA JSON array, satu objek per berita dengan field "i" (indeks input), "tickers",
"sentiment", "market". Tanpa penjelasan."""

_ARRAY = re.compile(r"\[.*\]", re.S)
_OBJ = re.compile(r"\{[^{}]*\}")


def _system() -> str:
    aliases = "; ".join(f"{k}={'/'.join(v[:2])}" for k, v in NAME_ALIASES.items())
    return SYSTEM.format(codes=", ".join(STOCKS), aliases=aliases)


def _parse(text: str) -> list[dict]:
    m = _ARRAY.search(text or "")
    if m:
        try:
            data = json.loads(m.group(0))
            return [d for d in data if isinstance(d, dict) and "i" in d]
        except json.JSONDecodeError:
            pass
    # fallback: output terpotong → ambil objek-objek yang utuh
    out: list[dict] = []
    for om in _OBJ.finditer(text or ""):
        try:
            d = json.loads(om.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and "i" in d:
            out.append(d)
    return out


async def analyze_pending(conn: sqlite3.Connection, limit: int = 120) -> int:
    """Analisis berita yang belum punya sentimen. Return jumlah yang berhasil."""
    rows = db.news_pending(conn, limit)
    if not rows:
        return 0
    done = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        payload = "\n".join(
            f"{i}. [{r['source']}] {r['title']} — {r['summary'][:160]}"
            for i, r in enumerate(chunk))
        try:
            res = await asyncio.wait_for(generate(_system(), payload), TIMEOUT_S)
        except Exception:
            log.warning("sentimen batch gagal", exc_info=True)
            continue
        if res.error:
            log.warning("sentimen: %s", res.error)
            continue
        by_i = {int(d["i"]): d for d in _parse(res.text) if str(d["i"]).isdigit()}
        for i, r in enumerate(chunk):
            d = by_i.get(i)
            if not d:
                continue
            tickers = [t for t in (d.get("tickers") or []) if isinstance(t, str) and t in STOCKS]
            # gabung dengan deteksi rule-based (ticker eksplisit di judul)
            for t in (r["tickers"] or "").split(","):
                if t and t not in tickers:
                    tickers.append(t)
            try:
                sent = max(-1, min(1, int(d.get("sentiment", 0))))
            except (TypeError, ValueError):
                sent = 0
            db.news_set_analysis(conn, r["id"], ",".join(tickers[:4]), sent,
                                 bool(d.get("market", bool(tickers))))
            done += 1
        conn.commit()
    log.info("sentimen: %d/%d dianalisis", done, len(rows))
    return done
