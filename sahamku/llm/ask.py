"""/ask — tanya Claude dengan konteks data saham dari DB."""

from __future__ import annotations

import logging
import re
import sqlite3

from sahamku import db, levels, news
from sahamku.analysis import premarket
from sahamku.config import DISCLAIMER
from sahamku.llm.providers import generate
from sahamku.pipeline import load_joined
from sahamku.signals.rules import RULE_LABELS
from sahamku.universe import active_codes, to_yf

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Kamu adalah Sahamku, asisten analisis teknikal saham Indonesia (IHSG/IDX).
Jawab dalam Bahasa Indonesia, ringkas (maks ~200 kata), berbasis data yang diberikan.
Gunakan format teks biasa (tanpa markdown heading), boleh bullet sederhana dengan "•".
Gunakan HANYA angka yang ada di data; jangan mengarang angka atau berita.
Jika data tidak cukup untuk menjawab, katakan apa adanya.
Jangan pernah memberi perintah beli/jual eksplisit; sampaikan sebagai skenario & level teknikal.
Akhiri jawaban dengan satu baris disclaimer singkat: "Bukan saran investasi."
"""

# Kode saham harus KAPITAL (atau diawali $) supaya kata biasa seperti "buka" tidak
# dianggap ticker BUKA. Contoh valid: "BBCA", "$bbca".
_CODE_RE = re.compile(r"(?<![A-Za-z])(?:\$([A-Za-z]{4})|([A-Z]{4}))(?![A-Za-z])")


def detect_codes(text: str, max_codes: int = 3,
                 conn: sqlite3.Connection | None = None) -> list[str]:
    found: list[str] = []
    known = set(active_codes(conn))
    for m in _CODE_RE.finditer(text):
        c = (m.group(1) or m.group(2)).upper()
        if c in known and c not in found:
            found.append(c)
    return found[:max_codes]


def build_context(conn: sqlite3.Connection, codes: list[str]) -> str:
    parts: list[str] = []
    pm = premarket.build(conn)
    if pm:
        glob = "; ".join(f"{n} {p:+.2f}%" for n, _, p in pm.global_rows if p is not None)
        pct = f"{pm.ihsg_pct:+.2f}%" if pm.ihsg_pct is not None else "n/a"
        rsi = f"{pm.ihsg_rsi:.1f}" if pm.ihsg_rsi is not None else "n/a"
        parts.append(
            f"[IHSG] tanggal data {pm.date}, close {pm.ihsg_close:,.0f} ({pct}), "
            f"RSI {rsi}, {pm.ihsg_trend}, support {pm.support:,.0f}, "
            f"resistance {pm.resistance:,.0f}. Sentimen global: {pm.sentiment_label}. "
            f"Global: {glob}"
        )
    market_news = news.headlines(conn, hours=24, limit=5)
    if market_news:
        parts.append("[Berita pasar 24 jam] " + " | ".join(
            f"{news.SENT_EMOJI.get(h.sentiment, '')}{h.title}" for h in market_news))
    for code in codes:
        t = to_yf(code)
        heads = news.headlines(conn, hours=72, code=code, limit=4)
        if heads:
            parts.append(f"[Berita {code} 72 jam] " + " | ".join(
                f"{news.SENT_EMOJI.get(h.sentiment, '')}{h.title}" for h in heads))
        j = load_joined(conn, t, limit=30)
        if j.empty:
            parts.append(f"[{code}] tidak ada data")
            continue
        last = j.iloc[-1]
        date_str = j.index[-1].strftime("%Y-%m-%d")
        bars = "\n".join(
            f"{d.strftime('%Y-%m-%d')} O{r.open:.0f} H{r.high:.0f} L{r.low:.0f} "
            f"C{r.close:.0f} V{r.volume / 1e6:.1f}jt"
            for d, r in j.tail(15).iterrows()
        )
        rating = db.rating_for(conn, t, date_str)
        sigs = [f"{RULE_LABELS.get(s['rule'], s['rule'])} ({s['detail']})"
                for s in db.signals_for(conn, t, date_str)]
        chg = (last["close"] / j["close"].iloc[-2] - 1) * 100 if len(j) > 1 else 0
        sr = levels.describe(levels.compute(db.load_ohlcv(conn, t)))
        parts.append(
            f"[{code}] data s/d {date_str}. Close {last['close']:.0f} ({chg:+.2f}%). "
            f"SMA20 {last['sma20']:.0f} SMA50 {last['sma50']:.0f} SMA200 {last['sma200']:.0f}. "
            f"RSI14 {last['rsi14']:.1f}. MACD {last['macd']:.1f} sig {last['macd_signal']:.1f}. "
            f"BB {last['bb_lower']:.0f}-{last['bb_upper']:.0f}. ATR {last['atr14']:.1f}. "
            f"Vol rata-rata 20D {last['vol_avg20'] / 1e6:.1f}jt. "
            f"Rating: {rating['rating'] if rating else 'n/a'}. "
            f"Sinyal aktif: {'; '.join(sigs) if sigs else 'tidak ada'}. "
            f"Support/resistance swing: {sr}.\n"
            f"15 bar terakhir:\n{bars}"
        )
    return "\n\n".join(parts)


async def ask(conn: sqlite3.Connection, question: str, chat_id: int | None = None) -> str:
    codes = detect_codes(question, conn=conn)
    # pertanyaan lanjutan tanpa kode: pakai kode dari giliran sebelumnya
    history = db.ask_history_recent(conn, chat_id) if chat_id else []
    if not codes and history:
        for _, t in reversed(history):
            if codes := detect_codes(t, conn=conn):
                break
    context = build_context(conn, codes)
    user_msg = f"Data terkini:\n{context}\n\nPertanyaan pengguna: {question}"
    res = await generate(SYSTEM_PROMPT, user_msg, history)
    if res.error:
        return res.error
    # model open-source kadang tetap memakai markdown; Telegram (HTML mode) menampilkannya mentah
    text = res.text.replace("**", "").replace("__", "")
    if not text:
        return "Maaf, tidak ada jawaban yang bisa diberikan."
    if "bukan saran investasi" not in text.lower():
        text += f"\n\n{DISCLAIMER}"
    if chat_id:
        db.ask_history_add(conn, chat_id, "user", question)
        db.ask_history_add(conn, chat_id, "assistant", text)
    return text
