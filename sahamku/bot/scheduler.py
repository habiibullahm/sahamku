"""Job terjadwal (WIB, hari bursa)."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from sahamku import db
from sahamku.analysis import aftermarket, premarket
from sahamku.config import TZ, settings
from sahamku.ingestion.eod import ingest, validate_eod
from sahamku.ingestion.global_ import ingest_global
from sahamku.pipeline import recompute_all
from sahamku.report import format as fmt
from sahamku.universe import is_trading_day

log = logging.getLogger(__name__)

EOD_RETRY_MINUTES = 15
EOD_DEADLINE = (18, 0)


def _hm(override: str | None, default: tuple[int, int]) -> tuple[int, int]:
    if override:
        h, m = override.split(":")
        return int(h), int(m)
    return default


def _today() -> date:
    return datetime.now(TZ).date()


async def _run_logged(job: str, fn, bot: Bot | None = None) -> str:
    """Bungkus job: catat ke job_runs, tangkap exception, beri tahu admin bila gagal."""
    with db.db() as conn:
        run_id = db.job_start(conn, job)
    try:
        detail = await fn()
        with db.db() as conn:
            db.job_finish(conn, run_id, "ok", detail or "")
        log.info("job %s ok: %s", job, detail)
        return "ok"
    except Exception as e:
        log.exception("job %s failed", job)
        with db.db() as conn:
            db.job_finish(conn, run_id, "error", repr(e))
        if bot and settings.admin_chat_id:
            try:
                await bot.send_message(
                    settings.admin_chat_id,
                    f"🚨 Job <b>{job}</b> gagal: <code>{type(e).__name__}: {str(e)[:300]}</code>")
            except Exception:
                log.warning("gagal kirim alert admin", exc_info=True)
        return "error"


async def _post_channel(bot: Bot, text: str) -> bool:
    """Broadcast ke channel publik (tanpa watchlist). Gagal tidak menghentikan job."""
    if not settings.channel_id:
        return False
    try:
        await bot.send_message(settings.channel_id, text)
        return True
    except Exception:
        log.warning("gagal post ke channel %s", settings.channel_id, exc_info=True)
        return False


# ---------- jobs ----------

async def job_ingest_global(bot: Bot) -> None:
    if not is_trading_day(_today()):
        return

    async def run():
        with db.db() as conn:
            c = await asyncio.to_thread(ingest_global, conn)
        return f"{len(c)} tickers"

    await _run_logged("ingest_global", run, bot)


async def job_premarket(bot: Bot) -> None:
    if not is_trading_day(_today()):
        return

    async def run():
        with db.db() as conn:
            ids = set(db.subscribed_chat_ids(conn))
            if settings.admin_chat_id:
                ids.add(settings.admin_chat_id)
            sent = 0
            for cid in ids:
                watch = db.watch_list(conn, cid)
                r = premarket.build(conn, for_date=_today(), watch_codes=watch)
                if not r:
                    continue
                try:
                    await bot.send_message(cid, fmt.premarket(r))
                    sent += 1
                    await asyncio.sleep(0.05)
                except TelegramForbiddenError:
                    db.set_subscribed(conn, cid, False)
                    log.info("chat %s memblokir bot → unsubscribe", cid)
                except Exception:
                    log.warning("gagal kirim premarket ke %s", cid, exc_info=True)
            r = premarket.build(conn, for_date=_today())
        ch = await _post_channel(bot, fmt.premarket(r, cta=True)) if r else False
        return f"sent to {sent} chats; channel={ch}"

    await _run_logged("premarket", run, bot)


async def job_eod_pipeline(bot: Bot, scheduler: AsyncIOScheduler, attempt: int = 1) -> None:
    """16:30: ingest → validate → compute → (17:00+) kirim. Retry jika data belum lengkap."""
    today = _today()
    if not is_trading_day(today):
        return

    async def run():
        with db.db() as conn:
            await asyncio.to_thread(ingest, conn)
            ok, missing = validate_eod(conn, today)
            await asyncio.to_thread(recompute_all, conn)
        now = datetime.now(TZ)
        deadline = now.replace(hour=EOD_DEADLINE[0], minute=EOD_DEADLINE[1], second=0)
        if not ok and now + timedelta(minutes=EOD_RETRY_MINUTES) <= deadline:
            nxt = now + timedelta(minutes=EOD_RETRY_MINUTES)
            scheduler.add_job(
                job_eod_pipeline, DateTrigger(run_date=nxt),
                args=[bot, scheduler, attempt + 1], id=f"eod_retry_{attempt}",
                replace_existing=True,
            )
            return f"incomplete ({len(missing)} missing), retry #{attempt + 1} at {nxt:%H:%M}"
        # kirim laporan (lengkap, atau parsial setelah deadline)
        send_at = now.replace(
            hour=_hm(settings.schedule_override_aftermarket, (17, 0))[0],
            minute=_hm(settings.schedule_override_aftermarket, (17, 0))[1], second=0)
        if now < send_at:
            scheduler.add_job(
                job_send_aftermarket, DateTrigger(run_date=send_at),
                args=[bot, missing], id="aftermarket_send", replace_existing=True,
            )
            return f"complete={ok}; report scheduled {send_at:%H:%M}"
        await job_send_aftermarket(bot, missing)
        return f"complete={ok}; report sent now"

    await _run_logged(f"eod_pipeline#{attempt}", run, bot)


async def job_send_aftermarket(bot: Bot, missing: list[str] | None = None) -> None:
    async def run():
        with db.db() as conn:
            ids = set(db.subscribed_chat_ids(conn))
            if settings.admin_chat_id:
                ids.add(settings.admin_chat_id)
            sent = 0
            for cid in ids:
                watch = db.watch_list(conn, cid)
                r = aftermarket.build(conn, watch_codes=watch, missing=missing)
                if not r:
                    continue
                try:
                    await bot.send_message(cid, fmt.aftermarket(r))
                    sent += 1
                    await asyncio.sleep(0.05)
                except TelegramForbiddenError:
                    db.set_subscribed(conn, cid, False)
                    log.info("chat %s memblokir bot → unsubscribe", cid)
                except Exception:
                    log.warning("gagal kirim aftermarket ke %s", cid, exc_info=True)
            r = aftermarket.build(conn, missing=missing)
        ch = await _post_channel(bot, fmt.aftermarket(r, cta=True)) if r else False
        return f"sent to {sent} chats; channel={ch}"

    await _run_logged("send_aftermarket", run, bot)


async def job_weekly_backtest(bot: Bot) -> None:
    from sahamku.backtest.run import run_backtest, summary_text

    async def run():
        with db.db() as conn:
            res = await asyncio.to_thread(run_backtest, conn)
        if settings.admin_chat_id:
            await bot.send_message(settings.admin_chat_id, summary_text(res))
        return f"{len(res)} rules"

    await _run_logged("weekly_backtest", run, bot)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    sch = AsyncIOScheduler(timezone=TZ)
    ph, pm = _hm(settings.schedule_override_premarket, (8, 15))
    eod_h, eod_m = (16, 30)
    if settings.schedule_override_aftermarket:
        # testing: ingest 2 menit sebelum jam kirim override
        h, m = _hm(settings.schedule_override_aftermarket, (17, 0))
        t = datetime(2000, 1, 1, h, m) - timedelta(minutes=2)
        eod_h, eod_m = t.hour, t.minute

    sch.add_job(job_ingest_global, CronTrigger(day_of_week="mon-fri", hour=7, minute=30),
                args=[bot], id="ingest_global")
    sch.add_job(job_premarket, CronTrigger(day_of_week="mon-fri", hour=ph, minute=pm),
                args=[bot], id="premarket")
    sch.add_job(job_eod_pipeline, CronTrigger(day_of_week="mon-fri", hour=eod_h, minute=eod_m),
                args=[bot, sch], id="eod_pipeline")
    sch.add_job(job_weekly_backtest, CronTrigger(day_of_week="sat", hour=9, minute=0),
                args=[bot], id="weekly_backtest")
    return sch
