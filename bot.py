import asyncio

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import (
    APP_API_HOST,
    APP_API_PORT,
    BOT_TOKEN,
    SUBSCRIPTION_REMINDER_INTERVAL_SECONDS,
    TRIAL_CHECK_INTERVAL_SECONDS,
)
from database import init_db
from handlers.admin import router as admin_router
from handlers.app_auth import router as app_auth_router
from handlers.menu import router as menu_router
from services.app_feedback_api import create_app
from services.subscription_reminder_service import SubscriptionReminderService


async def run_subscription_reminders(
    bot: Bot,
    stop_event: asyncio.Event,
    service: SubscriptionReminderService
):
    elapsed_reminder_seconds = SUBSCRIPTION_REMINDER_INTERVAL_SECONDS
    while not stop_event.is_set():
        try:
            if elapsed_reminder_seconds >= SUBSCRIPTION_REMINDER_INTERVAL_SECONDS:
                await service.send_due_reminders(bot)
                elapsed_reminder_seconds = 0
            await service.check_due_trials(bot)
        except Exception as error:
            print(f"Не удалось выполнить проверку сроков подписок: {error}")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=TRIAL_CHECK_INTERVAL_SECONDS
            )
        except TimeoutError:
            pass
        finally:
            elapsed_reminder_seconds += TRIAL_CHECK_INTERVAL_SECONDS


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

    reminder_stop_event = asyncio.Event()
    reminder_task = asyncio.create_task(
        run_subscription_reminders(
            bot,
            reminder_stop_event,
            SubscriptionReminderService()
        )
    )

    print("CosmoNet Bot запущен")

    try:
        await dp.start_polling(bot)
    finally:
        reminder_stop_event.set()
        await reminder_task
        await api_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
