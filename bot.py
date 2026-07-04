import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from handlers.admin import router as admin_router
from config import BOT_TOKEN
from database import init_db
from handlers.menu import router as menu_router


async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp.include_router(menu_router)
    dp.include_router(admin_router)

    print("CosmoNet Bot запущен")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())