import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_config
from .db import connect
from .handlers import router


import os
print("RUNNING FROM:", os.getcwd())


async def main():
    cfg = load_config()
    print("DB_PATH(from cfg):", repr(cfg.db_path))
    print("DB_PATH(abs):", os.path.abspath(cfg.db_path))
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