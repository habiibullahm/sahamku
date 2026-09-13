"""Command handlers aiogram."""

from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from sahamku import alerts, db, levels, news, screener
from sahamku.analysis import aftermarket, compare, growth, premarket, sector
from sahamku.config import settings
from sahamku.llm import narrative
from sahamku.llm.ask import ask as llm_ask
from sahamku.pipeline import load_joined
from sahamku.report import chart
from sahamku.report import format as fmt
from sahamku.signals.rules import RULE_LABELS
from sahamku.universe import IHSG, active_codes, is_known_code, to_yf, universe_label

log = logging.getLogger(__name__)
router = Router()
# matplotlib/pyplot tidak thread-safe → render chart satu per satu
_chart_lock = asyncio.Lock()

HELP = """<b>Sahamku</b> — daily scan saham IHSG

/scan — laporan after-market terbaru
/growth — ranking Potential Growth terbaru
/stock KODE — snapshot + chart (contoh: /stock BBCA)
/watch KODE — tambah ke watchlist
/unwatch KODE — hapus dari watchlist
/watchlist — lihat watchlist
/ihsg — snapshot IHSG + chart + support/resistance
/news [KODE] — berita pasar / emiten dengan sentimen
/screener FILTER — filter saham (contoh: /screener rsi&lt;35 above200)
/compare A B C — bandingkan 2–4 saham + chart
/sector — ringkasan per sektor
/alert KODE > HARGA — alert level (contoh: /alert BBCA > 6500, /alert BBRI rsi < 30)
/alerts — daftar alert · /unalert ID — hapus alert
/ask pertanyaan — tanya AI (contoh: /ask kenapa BBCA turun?)
/settings — atur laporan mana yang diterima
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
        narr = await narrative.get_or_create(
            conn, "aftermarket", r.date, fmt.aftermarket(aftermarket.build(conn)))
    await m.answer(fmt.aftermarket(r, narrative=narr))


@router.message(Command("growth"))
async def cmd_growth(m: types.Message) -> None:
    with db.db() as conn:
        date_str, rows = growth.latest(conn, limit=20)
        label = universe_label(conn)
    if not date_str:
        await m.answer("Belum ada hasil scan. Jalankan pipeline EOD terlebih dahulu.")
        return
    await m.answer(fmt.growth_report(date_str, rows, label))


@router.message(Command("stock"))
async def cmd_stock(m: types.Message, command: CommandObject) -> None:
    code = _code_arg(command)
    if not code:
        await m.answer("Format: /stock KODE (contoh: /stock BBCA)")
        return
    t = to_yf(code)
    with db.db() as conn:
        if not is_known_code(code, conn):
            await m.answer(f"{code} tidak ada di universe ({len(active_codes(conn))} saham).")
            return
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
    with db.db() as conn:
        heads = news.headlines(conn, hours=72, code=code, limit=3)
        watching = code in db.watch_list(conn, m.chat.id)
    text = fmt.stock_snapshot(
        code, date_str, float(last["close"]), pct, float(last["volume"]), ind,
        rating["rating"] if rating else None, rating["score"] if rating else None, rules,
        headlines=heads, sr=levels.describe(levels.compute(j)),
    )
    async with _chart_lock:
        png = await asyncio.to_thread(chart.render, code, j)
    # caption Telegram maks 1024 char → kirim chart dan teks terpisah
    await m.answer_photo(FSInputFile(png))
    await m.answer(text, reply_markup=_stock_keyboard(code, watching))


def _stock_keyboard(code: str, watching: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📰 Berita", callback_data=f"news:{code}"),
        InlineKeyboardButton(text=("👀 Unwatch" if watching else "👀 Watch"),
                             callback_data=f"watch:{code}"),
        InlineKeyboardButton(text="🤖 Tanya AI", callback_data=f"ask:{code}"),
    ]])


@router.callback_query(F.data.startswith("news:"))
async def cb_news(cq: CallbackQuery) -> None:
    code = cq.data.split(":", 1)[1]
    with db.db() as conn:
        items = news.headlines(conn, hours=72, code=code, limit=8)
    await cq.message.answer(fmt.news_list(code, items, 72))
    await cq.answer()


@router.callback_query(F.data.startswith("watch:"))
async def cb_watch(cq: CallbackQuery) -> None:
    code = cq.data.split(":", 1)[1]
    chat_id = cq.message.chat.id
    with db.db() as conn:
        db.upsert_user(conn, chat_id, cq.from_user.username if cq.from_user else None)
        if code in db.watch_list(conn, chat_id):
            db.watch_remove(conn, chat_id, code)
            watching, note = False, f"{code} dihapus dari watchlist"
        else:
            db.watch_add(conn, chat_id, code)
            watching, note = True, f"{code} ditambahkan ke watchlist"
    try:
        await cq.message.edit_reply_markup(reply_markup=_stock_keyboard(code, watching))
    except Exception:
        pass
    await cq.answer(note)


@router.callback_query(F.data.startswith("ask:"))
async def cb_ask(cq: CallbackQuery) -> None:
    code = cq.data.split(":", 1)[1]
    await cq.answer()
    await _run_ask(cq.message, cq.message.chat.id,
                   f"Analisis singkat {code}: kondisi teknikal saat ini, level penting, "
                   f"dan skenario yang perlu diperhatikan.")


@router.callback_query(F.data.startswith("pref:"))
async def cb_pref(cq: CallbackQuery) -> None:
    key = cq.data.split(":", 1)[1]
    chat_id = cq.message.chat.id
    with db.db() as conn:
        if key in db.PREF_KEYS:
            db.prefs_toggle(conn, chat_id, key)
        prefs, sub = db.prefs_get(conn, chat_id), db.is_subscribed(conn, chat_id)
    try:
        await cq.message.edit_text(fmt.settings_text(prefs, sub),
                                   reply_markup=_settings_keyboard(prefs))
    except Exception:
        pass
    await cq.answer("Tersimpan")


def _settings_keyboard(prefs: dict[str, bool]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"{'✅' if prefs[k] else '⬜'} {label}", callback_data=f"pref:{k}")]
        for k, label in fmt.PREF_LABELS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def cmd_settings(m: types.Message) -> None:
    with db.db() as conn:
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        prefs, sub = db.prefs_get(conn, m.chat.id), db.is_subscribed(conn, m.chat.id)
    await m.answer(fmt.settings_text(prefs, sub), reply_markup=_settings_keyboard(prefs))


@router.message(Command("admin"))
async def cmd_admin(m: types.Message, command: CommandObject) -> None:
    if m.chat.id != settings.admin_chat_id:
        await m.answer("Perintah ini hanya untuk admin.")
        return
    args = (command.args or "").strip()
    sub, _, rest = args.partition(" ")
    with db.db() as conn:
        if sub in ("pro", "free") and rest.strip().lstrip("-").isdigit():
            ok = db.plan_set(conn, int(rest.strip()), sub)
            await m.answer(f"Plan {rest.strip()} → {sub}" if ok else "chat_id tidak ditemukan.")
            return
        if sub == "broadcast" and rest.strip():
            ids = db.subscribed_chat_ids(conn)
            sent = 0
            for cid in ids:
                try:
                    await m.bot.send_message(cid, f"📣 {escape(rest.strip())}")
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    log.warning("broadcast gagal ke %s", cid, exc_info=True)
            await m.answer(f"Broadcast terkirim ke {sent}/{len(ids)} user.")
            return
        st, jobs = db.admin_stats(conn), db.job_runs_recent(conn)
    await m.answer(fmt.admin_stats_text(st, jobs) +
                   "\n\nPerintah: /admin · /admin broadcast &lt;pesan&gt; · "
                   "/admin pro|free &lt;chat_id&gt;")


@router.message(Command("ihsg"))
async def cmd_ihsg(m: types.Message) -> None:
    with db.db() as conn:
        j = load_joined(conn, IHSG)
    if j.empty:
        await m.answer("Data IHSG belum tersedia.")
        return
    last = j.iloc[-1]
    date_str = j.index[-1].strftime("%Y-%m-%d")
    pct = (last["close"] / j["close"].iloc[-2] - 1) * 100 if len(j) > 1 else None
    ind = {k: (None if last[k] != last[k] else float(last[k]))
           for k in ("sma20", "sma50", "sma200", "rsi14", "macd", "macd_signal")}
    text = fmt.ihsg_snapshot(
        date_str, float(last["close"]), pct, float(last["volume"]), ind,
        float(j["low"].tail(20).min()), float(j["high"].tail(20).max()),
        premarket.trend_label(last), sr=levels.describe(levels.compute(j)),
    )
    async with _chart_lock:
        png = await asyncio.to_thread(chart.render, "IHSG", j)
    await m.answer_photo(FSInputFile(png))
    await m.answer(text)


@router.message(Command("news"))
async def cmd_news(m: types.Message, command: CommandObject) -> None:
    code = _code_arg(command)
    hours = 72 if code else 24
    with db.db() as conn:
        if code and not is_known_code(code, conn):
            await m.answer(f"{code} tidak ada di universe aktif.")
            return
        items = news.headlines(conn, hours=hours, code=code, limit=10)
    await m.answer(fmt.news_list(code, items, hours))


@router.message(Command("screener"))
async def cmd_screener(m: types.Message, command: CommandObject) -> None:
    q = screener.parse(command.args or "")
    if q.empty or q.errors:
        msg = screener.HELP
        if q.errors:
            msg = f"Filter tidak dikenal: <code>{escape(' '.join(q.errors))}</code>\n\n" + msg
        await m.answer(msg)
        return
    with db.db() as conn:
        date_str, rows = await asyncio.to_thread(screener.run, conn, q)
    if not date_str:
        await m.answer("Data belum tersedia.")
        return
    await m.answer(fmt.screener_result(date_str, q, rows))


@router.message(Command("alert"))
async def cmd_alert(m: types.Message, command: CommandObject) -> None:
    with db.db() as conn:
        spec = alerts.parse(command.args or "", conn)
    if isinstance(spec, str):
        await m.answer(spec)
        return
    with db.db() as conn:
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        lim = _limits(conn, m.chat.id)
        if db.alert_count(conn, m.chat.id) >= lim["alerts"]:
            tier = "" if lim["pro"] else " di tier Free"
            await m.answer(f"Maksimal {lim['alerts']} alert aktif{tier}. "
                           "Hapus dulu dengan /unalert ID.")
            return
        aid = db.alert_add(conn, m.chat.id, spec.code, spec.metric, spec.op, spec.value)
    await m.answer(f"🔔 Alert #{aid} dibuat: <b>{escape(spec.label())}</b>\n"
                   "Dicek tiap 15 menit selama jam bursa (harga delayed) dan setelah penutupan; "
                   "sekali kirim.")


@router.message(Command("alerts"))
async def cmd_alerts(m: types.Message) -> None:
    with db.db() as conn:
        rows = db.alert_list(conn, m.chat.id)
    if not rows:
        await m.answer("Belum ada alert. Buat dengan /alert KODE > HARGA.")
        return
    lines = ["🔔 <b>Alert aktif</b>"]
    for r in rows:
        spec = alerts.AlertSpec(r["code"], r["metric"], r["op"], float(r["value"]))
        lines.append(f"  #{r['id']} — {escape(spec.label())}")
    lines.append("\nHapus: /unalert ID")
    await m.answer("\n".join(lines))


@router.message(Command("unalert"))
async def cmd_unalert(m: types.Message, command: CommandObject) -> None:
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdigit():
        await m.answer("Format: /unalert ID (lihat /alerts)")
        return
    with db.db() as conn:
        ok = db.alert_remove(conn, m.chat.id, int(arg))
    await m.answer(f"🗑 Alert #{arg} dihapus." if ok else f"Alert #{arg} tidak ditemukan.")


@router.message(Command("watch"))
async def cmd_watch(m: types.Message, command: CommandObject) -> None:
    code = _code_arg(command)
    with db.db() as conn:
        if not code or not is_known_code(code, conn):
            await m.answer("Format: /watch KODE (kode dari universe aktif)")
            return
        db.upsert_user(conn, m.chat.id, m.from_user.username if m.from_user else None)
        lim = _limits(conn, m.chat.id)
        if code not in db.watch_list(conn, m.chat.id) and \
                db.watch_count(conn, m.chat.id) >= lim["watch"]:
            tier = "" if lim["pro"] else " di tier Free"
            await m.answer(f"Watchlist maksimal {lim['watch']} saham{tier}. "
                           "Hapus dulu dengan /unwatch.")
            return
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
        await m.answer("Format: /ask pertanyaan (contoh: /ask kenapa BBCA turun?)\n"
                       "Pertanyaan lanjutan boleh tanpa kode saham (bot ingat 2 jam). "
                       "/ask clear untuk mulai percakapan baru.")
        return
    if q.lower() in ("clear", "reset"):
        with db.db() as conn:
            db.ask_history_clear(conn, m.chat.id)
        await m.answer("🧹 Riwayat percakapan /ask dihapus.")
        return
    await _run_ask(m, m.chat.id, q)


async def _run_ask(m: types.Message, chat_id: int, q: str) -> None:
    is_admin = settings.admin_chat_id == chat_id
    with db.db() as conn:
        limit = _limits(conn, chat_id)["ask"]
        used = db.ask_count_today(conn, chat_id)
        if not is_admin and used >= limit:
            await m.answer(f"⏳ Kuota /ask hari ini habis ({limit}/hari). "
                           "Coba lagi besok, atau lihat /stock KODE dan /scan.")
            return
        if not is_admin:
            used = db.ask_increment(conn, chat_id)
    sisa = "" if is_admin else f" · sisa kuota {limit - used}"
    thinking = await m.answer(f"🤔 Menganalisis…{sisa}")
    try:
        with db.db() as conn:
            answer = await llm_ask(conn, q, chat_id=chat_id)
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


def _limits(conn, chat_id: int) -> dict[str, int]:
    pro = db.plan_get(conn, chat_id) == "pro" or chat_id == settings.admin_chat_id
    return {
        "ask": settings.pro_ask_daily_limit if pro else settings.ask_daily_limit,
        "watch": settings.pro_watchlist_max if pro else settings.free_watchlist_max,
        "alerts": settings.pro_alerts_max if pro else settings.free_alerts_max,
        "pro": pro,
    }


@router.message(Command("compare"))
async def cmd_compare(m: types.Message, command: CommandObject) -> None:
    codes = [c.upper() for c in (command.args or "").split()][:compare.MAX_CODES]
    with db.db() as conn:
        bad = [c for c in codes if not is_known_code(c, conn)]
    if len(codes) < 2 or bad:
        await m.answer("Format: /compare KODE1 KODE2 [KODE3 KODE4] (2–4 saham dari universe)"
                       + (f"\nTidak dikenal: {', '.join(bad)}" if bad else ""))
        return
    with db.db() as conn:
        rows, series = await asyncio.to_thread(compare.build, conn, codes)
    if len(rows) < 2:
        await m.answer("Data belum cukup untuk dibandingkan.")
        return
    async with _chart_lock:
        png = await asyncio.to_thread(compare.render_chart, series)
    await m.answer_photo(FSInputFile(png))
    await m.answer(fmt.compare(rows))


@router.message(Command("sector"))
async def cmd_sector(m: types.Message) -> None:
    with db.db() as conn:
        date_str, rows = await asyncio.to_thread(sector.build, conn)
    if not rows:
        await m.answer("Data belum tersedia.")
        return
    await m.answer(fmt.sector(date_str, rows))


def _code_arg(command: CommandObject) -> str | None:
    args = (command.args or "").strip().upper()
    return args.split()[0] if args else None
