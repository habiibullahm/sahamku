"""Kirim & pin pesan "cara pakai" di channel.

Usage: python scripts/channel_pin.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402

from sahamku.config import DISCLAIMER, settings  # noqa: E402

PINNED = f"""📌 <b>Selamat datang di Sahamku Daily</b>

Ringkasan harian saham liquid IDX, otomatis setiap hari bursa:

🌅 <b>08:15 WIB — Pre-Market</b>
Sentimen global semalam, level support/resistance IHSG, catatan sektor, sinyal dari scan kemarin.

📊 <b>17:00 WIB — After-Market</b>
IHSG, top gainers/losers, sinyal teknikal bullish/bearish beserta alasannya, Bollinger squeeze.

<b>Arti rating</b>
🟢 bullish — skor sinyal ≥ +2 · 🔴 bearish — skor ≤ −2 · ⚪ netral
Rule teknikal: RSI, MACD, breakout 20 hari + volume, golden/death cross, posisi vs SMA200.

🤖 <b>Ingin lebih dalam?</b> Buka @{settings.bot_username}:
/stock KODE — snapshot + chart · /watch KODE — watchlist pribadi · /ask — tanya AI berbasis data

<i>{DISCLAIMER}</i>"""


async def main() -> None:
    dry = "--dry-run" in sys.argv
    if dry:
        print(PINNED)
        return
    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        msg = await bot.send_message(settings.channel_id, PINNED, disable_web_page_preview=True)
        await bot.pin_chat_message(settings.channel_id, msg.message_id, disable_notification=True)
        print(f"pinned message_id={msg.message_id}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
