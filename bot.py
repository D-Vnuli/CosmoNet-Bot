import asyncio

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import APP_API_HOST, APP_API_PORT, BOT_TOKEN
from database import init_db
from handlers.admin import router as admin_router
from handlers.app_auth import router as app_auth_router
from handlers.menu import router as menu_router
from services.app_feedback_api import create_app


async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp.include_router(app_auth_router)
    dp.include_router(menu_router)
    dp.include_router(admin_router)

    api_runner = web.AppRunner(create_app(bot))
    await api_runner.setup()
    api_site = web.TCPSite(api_runner, APP_API_HOST, APP_API_PORT)
    await api_site.start()

    print("CosmoNet Bot запущен")

    try:
        await dp.start_polling(bot)
    finally:
        await api_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())