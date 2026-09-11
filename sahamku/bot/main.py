"""Entry point: python -m sahamku.bot.main"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from sahamku import db
from sahamku.bot.handlers import router
from sahamku.bot.scheduler import build_scheduler
from sahamku.config import settings

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="scan", description="Laporan after-market terbaru"),
    BotCommand(command="stock", description="Snapshot + chart, contoh: /stock BBCA"),
    BotCommand(command="watch", description="Tambah ke watchlist"),
    BotCommand(command="unwatch", description="Hapus dari watchlist"),
    BotCommand(command="watchlist", description="Lihat watchlist"),
    BotCommand(command="ask", description="Tanya AI tentang saham"),
    BotCommand(command="stop", description="Berhenti menerima laporan otomatis"),
    BotCommand(command="resume", description="Aktifkan lagi laporan otomatis"),
    BotCommand(command="help", description="Bantuan"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN belum diisi di .env")
    db.init_db()

    bot = Bot(settings.telegram_bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands(COMMANDS)

    scheduler = build_scheduler(bot)
    scheduler.start()
    for j in scheduler.get_jobs():
        log.info("job %s next run %s", j.id, j.next_run_time)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
