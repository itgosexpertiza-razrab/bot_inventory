import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_config
from .db import connect
from .handlers import router


async def main():
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    db = connect(cfg.db_path)

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp["db"] = db
    dp["cfg"] = cfg

    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
