"""Command handlers aiogram."""

from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import FSInputFile

from sahamku import db
from sahamku.analysis import aftermarket
from sahamku.config import settings
from sahamku.llm.ask import ask as llm_ask
from sahamku.pipeline import load_joined
from sahamku.report import chart
from sahamku.report import format as fmt
from sahamku.signals.rules import RULE_LABELS
from sahamku.universe import is_known_code, to_yf

log = logging.getLogger(__name__)
router = Router()
# matplotlib/pyplot tidak thread-safe → render chart satu per satu
_chart_lock = asyncio.Lock()

HELP = """<b>Sahamku</b> — daily scan saham LQ45

/scan — laporan after-market terbaru
/stock KODE — snapshot + chart (contoh: /stock BBCA)
/watch KODE — tambah ke watchlist
/unwatch KODE — hapus dari watchlist
/watchlist — lihat watchlist
/ask pertanyaan — tanya AI (contoh: /ask kenapa BBCA turun?)
/stop — berhenti menerima laporan otomatis · /resume — aktifkan lagi

Laporan otomatis: pre-market 08:15 & after-market 17:00 WIB (hari bursa).
Kuota /ask: {limit} pertanyaan per hari.
"""


@router.message(CommandStart())
async def cmd_start(m: types.Message) -> None:
    with db.db() as conn:
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        db.set_subscribed(conn, m.chat.id, True)
    await m.answer(HELP.format(limit=settings.ask_daily_limit))


@router.message(Command("help"))
async def cmd_help(m: types.Message) -> None:
    await m.answer(HELP.format(limit=settings.ask_daily_limit))


@router.message(Command("stop"))
async def cmd_stop(m: types.Message) -> None:
    with db.db() as conn:
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        db.set_subscribed(conn, m.chat.id, False)
    await m.answer("🔕 Laporan otomatis dimatikan. Perintah lain tetap bisa dipakai. "
                   "Kirim /resume untuk mengaktifkan lagi.")


@router.message(Command("resume"))
async def cmd_resume(m: types.Message) -> None:
    with db.db() as conn:
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        db.set_subscribed(conn, m.chat.id, True)
    await m.answer("🔔 Laporan otomatis diaktifkan: pre-market 08:15 & after-market 17:00 WIB.")


@router.message(Command("scan"))
async def cmd_scan(m: types.Message) -> None:
    with db.db() as conn:
        watch = db.watch_list(conn, m.chat.id)
        r = aftermarket.build(conn, watch_codes=watch)
    if not r:
        await m.answer("Belum ada data. Jalankan backfill dulu.")
        return
    await m.answer(fmt.aftermarket(r))


@router.message(Command("stock"))
async def cmd_stock(m: types.Message, command: CommandObject) -> None:
    code = _code_arg(command)
    if not code:
        await m.answer("Format: /stock KODE (contoh: /stock BBCA)")
        return
    if not is_known_code(code):
        await m.answer(f"{code} tidak ada di universe LQ45.")
        return
    t = to_yf(code)
    with db.db() as conn:
        j = load_joined(conn, t)
        if j.empty:
            await m.answer("Data belum tersedia.")
            return
        last = j.iloc[-1]
        date_str = j.index[-1].strftime("%Y-%m-%d")
        pct = (last["close"] / j["close"].iloc[-2] - 1) * 100 if len(j) > 1 else None
        rating = db.rating_for(conn, t, date_str)
        rules = [
            f"{RULE_LABELS.get(s['rule'], s['rule'])} ({s['detail']})"
            for s in db.signals_for(conn, t, date_str)
        ]
    ind = {k: (None if last[k] != last[k] else float(last[k]))
           for k in ("sma20", "sma50", "sma200", "rsi14", "macd", "macd_signal",
                     "bb_lower", "bb_upper", "atr14")}
    text = fmt.stock_snapshot(
        code, date_str, float(last["close"]), pct, float(last["volume"]), ind,
        rating["rating"] if rating else None, rating["score"] if rating else None, rules,
    )
    async with _chart_lock:
        png = await asyncio.to_thread(chart.render, code, j)
    # caption Telegram maks 1024 char → kirim chart dan teks terpisah
    await m.answer_photo(FSInputFile(png))
    await m.answer(text)


@router.message(Command("watch"))
async def cmd_watch(m: types.Message, command: CommandObject) -> None:
    code = _code_arg(command)
    if not code or not is_known_code(code):
        await m.answer("Format: /watch KODE (kode LQ45)")
        return
    with db.db() as conn:
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        added = db.watch_add(conn, m.chat.id, code)
    await m.answer(f"✅ {code} ditambahkan." if added else f"{code} sudah ada di watchlist.")


@router.message(Command("unwatch"))
async def cmd_unwatch(m: types.Message, command: CommandObject) -> None:
    code = _code_arg(command)
    if not code:
        await m.answer("Format: /unwatch KODE")
        return
    with db.db() as conn:
        removed = db.watch_remove(conn, m.chat.id, code)
    await m.answer(f"🗑 {code} dihapus." if removed else f"{code} tidak ada di watchlist.")


@router.message(Command("watchlist"))
async def cmd_watchlist(m: types.Message) -> None:
    with db.db() as conn:
        codes = db.watch_list(conn, m.chat.id)
    if not codes:
        await m.answer("Watchlist kosong. Tambah dengan /watch KODE.")
        return
    await m.answer("👀 Watchlist: " + ", ".join(f"<code>{c}</code>" for c in codes))


@router.message(Command("ask"))
async def cmd_ask(m: types.Message, command: CommandObject) -> None:
    q = (command.args or "").strip()
    if not q:
        await m.answer("Format: /ask pertanyaan (contoh: /ask kenapa BBCA turun?)")
        return
    is_admin = settings.admin_chat_id == m.chat.id
    with db.db() as conn:
        used = db.ask_count_today(conn, m.chat.id)
        if not is_admin and used >= settings.ask_daily_limit:
            await m.answer(f"⏳ Kuota /ask hari ini habis ({settings.ask_daily_limit}/hari). "
                           "Coba lagi besok, atau lihat /stock KODE dan /scan.")
            return
        if not is_admin:
            used = db.ask_increment(conn, m.chat.id)
    sisa = "" if is_admin else f" · sisa kuota {settings.ask_daily_limit - used}"
    thinking = await m.answer(f"🤔 Menganalisis…{sisa}")
    try:
        with db.db() as conn:
            answer = await llm_ask(conn, q)
    except Exception:
        log.exception("ask failed")
        answer = "❌ Terjadi kesalahan saat memproses pertanyaan."
    # clip sebelum escape, sisakan ruang untuk entitas HTML (&amp; dll)
    await thinking.edit_text(escape(fmt.clip_plain(answer, 3800)))


@router.message(F.text)
async def cmd_unknown(m: types.Message) -> None:
    """Fallback: harus terdaftar paling akhir agar command di atas diprioritaskan."""
    text = (m.text or "").strip()
    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0]
        await m.answer(f"Perintah <code>{escape(cmd)}</code> tidak dikenal. Ketik /help.")
    else:
        await m.answer("Saya hanya merespons perintah. Ketik /help untuk daftar perintah, "
                       "atau /ask &lt;pertanyaan&gt; untuk bertanya ke AI.")


def _code_arg(command: CommandObject) -> str | None:
    args = (command.args or "").strip().upper()
    return args.split()[0] if args else None
