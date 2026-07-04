from html import escape

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from services.xui_service import XUIService, format_expiry_time
from config import ADMIN_IDS
from database import get_all_telegram_ids, get_all_users

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

    telegram_ids = get_all_telegram_ids()
    total_users = len(telegram_ids)
    xui = XUIService()
    result = await xui.get_all_clients()

    if not result["success"]:
        await message.answer(
            "📊 <b>Статистика CosmoNet</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            f"👥 <b>Пользователей бота:</b> {total_users}\n\n"
            "❌ Не удалось получить актуальные статусы из 3X-UI.\n\n"
            f"Ошибка: {escape(str(result['error']))}"
        )
        return

    clients = result["clients"]
    active_profiles = sum(
        1
        for client in clients
        if client.get("enable", False)
    )
    disabled_profiles = len(clients) - active_profiles
    telegram_id_strings = {str(telegram_id) for telegram_id in telegram_ids}
    linked_telegram_ids = {
        str(client.get("email"))
        for client in clients
        if str(client.get("email")) in telegram_id_strings
    }

    await message.answer(
        "📊 <b>Статистика CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Пользователей бота:</b> {total_users}\n"
        f"🔗 <b>VPN-профилей в 3X-UI:</b> {len(clients)}\n"
        f"🟢 <b>Активных VPN-профилей:</b> {active_profiles}\n"
        f"🔴 <b>Отключённых VPN-профилей:</b> {disabled_profiles}\n"
        f"🔄 <b>Связано с пользователями бота:</b> {len(linked_telegram_ids)}\n\n"
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

    telegram_ids = [user[0] for user in users]
    xui = XUIService()
    result = await xui.get_clients_by_emails(telegram_ids)

    if not result["success"]:
        await message.answer(
            "👥 <b>Последние пользователи</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "❌ Не удалось получить актуальные статусы из 3X-UI.\n\n"
            f"Ошибка: {escape(str(result['error']))}"
        )
        return

    clients = result["clients"]
    text = "👥 <b>Последние пользователи</b>\n\n━━━━━━━━━━━━━━\n\n"

    for index, user in enumerate(users, start=1):
        telegram_id, username, first_name, _registered_at = user
        client = clients.get(str(telegram_id))

        if not client:
            status_text = "🔴 VPN-профиль не создан"
            until_text = "—"
        elif client.get("enable", False):
            status_text = "🟢 активна"
            until_text = format_expiry_time(client.get("expiry_time"))
        else:
            status_text = "🟠 отключена"
            until_text = format_expiry_time(client.get("expiry_time"))

        username_text = f"@{escape(username)}" if username else "без username"
        first_name_text = escape(first_name) if first_name else "Без имени"

        text += (
            f"{index}. <b>{first_name_text}</b>\n"
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
