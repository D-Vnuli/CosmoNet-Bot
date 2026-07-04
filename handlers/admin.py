from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from services.xui_service import XUIService
from config import ADMIN_IDS
from database import get_all_users, get_users_stats
from keyboards.main_menu import main_menu

router = Router()


admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Админ: статистика")],
        [KeyboardButton(text="👥 Админ: пользователи")],
        [KeyboardButton(text="🔌 Тест 3X-UI")],
        [KeyboardButton(text="⬅️ Главное меню")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Админ-панель"
)


def is_admin(message: Message) -> bool:
    return message.from_user.id in ADMIN_IDS


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message):
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "🛠 <b>Админ-панель CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Выберите раздел ниже:",
        reply_markup=admin_menu
    )


@router.message(F.text == "📊 Админ: статистика")
async def admin_stats(message: Message):
    if not is_admin(message):
        return

    stats = get_users_stats()

    await message.answer(
        "📊 <b>Статистика CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Всего пользователей:</b> {stats['total_users']}\n"
        f"🟢 <b>Активных подписок:</b> {stats['active_users']}\n"
        f"🔴 <b>Без подписки:</b> {stats['inactive_users']}\n\n"
        "━━━━━━━━━━━━━━"
    )


@router.message(F.text == "👥 Админ: пользователи")
async def admin_users(message: Message):
    if not is_admin(message):
        return

    users = get_all_users(limit=20)

    if not users:
        await message.answer("👥 Пользователей пока нет.")
        return

    text = "👥 <b>Последние пользователи</b>\n\n━━━━━━━━━━━━━━\n\n"

    for index, user in enumerate(users, start=1):
        telegram_id, username, first_name, status, subscription_until, tariff, registered_at = user

        status_text = "🟢 активна" if status == "active" else "🔴 нет подписки"
        username_text = f"@{username}" if username else "без username"
        until_text = subscription_until if subscription_until else "—"

        text += (
            f"{index}. <b>{first_name or 'Без имени'}</b>\n"
            f"   {username_text}\n"
            f"   ID: <code>{telegram_id}</code>\n"
            f"   Статус: {status_text}\n"
            f"   До: {until_text}\n\n"
        )

    await message.answer(text)

@router.message(F.text == "🔌 Тест 3X-UI")
@router.message(Command("xui_test"))
async def xui_test(message: Message):
    if not is_admin(message):
        return

    xui = XUIService()
    result = await xui.get_inbounds()

    if not result["success"]:
        await message.answer(
            "🔌 <b>Тест 3X-UI</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            f"❌ Ошибка: {result['error']}"
        )
        return

    inbounds = result["inbounds"]

    await message.answer(
        "🔌 <b>Тест 3X-UI</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "✅ Подключение успешно\n"
        f"📡 Найдено inbound'ов: <b>{len(inbounds)}</b>"
    )