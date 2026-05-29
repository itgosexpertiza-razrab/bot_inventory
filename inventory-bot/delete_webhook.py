import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()

async def main():
    token = os.getenv("BOT_TOKEN")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    res = await bot.delete_webhook(drop_pending_updates=True)
    print("delete_webhook:", res)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())