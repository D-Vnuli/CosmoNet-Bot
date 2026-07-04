from html import escape

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from services.broadcast_service import (
    AudienceLoadError,
    BroadcastAudience,
    broadcast_service,
)
from services.xui_service import XUIService, format_expiry_time
from config import ADMIN_IDS
from database import get_all_telegram_ids, get_all_users

router = Router()


admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Админ: статистика")],
        [KeyboardButton(text="👥 Админ: пользователи")],
        [KeyboardButton(text="📣 Рассылка")],
        [KeyboardButton(text="🔌 Тест 3X-UI")],
        [KeyboardButton(text="⬅️ Главное меню")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Админ-панель"
)


audience_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Все пользователи")],
        [KeyboardButton(text="🟢 Активные подписчики")],
        [KeyboardButton(text="🔴 Без активной подписки")],
        [KeyboardButton(text="❌ Отмена")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите получателей"
)


cancel_broadcast_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
    input_field_placeholder="Отправьте текст или одну фотографию"
)


class BroadcastStates(StatesGroup):
    choosing_audience = State()
    waiting_content = State()


def is_admin(message: Message) -> bool:
    return message.from_user.id in ADMIN_IDS


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message):
        await message.answer("⛔ Доступ запрещён.")
        return

    await state.clear()

    await message.answer(
        "🛠 <b>Админ-панель CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Выберите раздел ниже:",
        reply_markup=admin_menu
    )


@router.message(F.text == "📣 Рассылка")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message):
        return

    if broadcast_service.is_running:
        await message.answer(
            "⏳ Предыдущая рассылка ещё выполняется. "
            "Дождитесь итогового отчёта."
        )
        return

    await state.set_state(BroadcastStates.choosing_audience)
    await message.answer(
        "📣 <b>Новая рассылка</b>\n\n"
        "Выберите группу получателей:",
        reply_markup=audience_menu
    )


@router.message(
    BroadcastStates.choosing_audience,
    Command("cancel")
)
@router.message(
    BroadcastStates.waiting_content,
    Command("cancel")
)
@router.message(
    BroadcastStates.choosing_audience,
    F.text == "❌ Отмена"
)
@router.message(
    BroadcastStates.waiting_content,
    F.text == "❌ Отмена"
)
async def broadcast_cancel(message: Message, state: FSMContext):
    if not is_admin(message):
        return

    await state.clear()
    await message.answer(
        "❌ Рассылка отменена.",
        reply_markup=admin_menu
    )


@router.message(BroadcastStates.choosing_audience)
async def broadcast_choose_audience(message: Message, state: FSMContext):
    if not is_admin(message):
        return

    audiences = {
        "👥 Все пользователи": BroadcastAudience.ALL,
        "🟢 Активные подписчики": BroadcastAudience.ACTIVE,
        "🔴 Без активной подписки": BroadcastAudience.INACTIVE,
    }
    audience = audiences.get(message.text)

    if not audience:
        await message.answer(
            "Выберите одну из групп с помощью кнопок ниже.",
            reply_markup=audience_menu
        )
        return

    await state.update_data(audience=audience.value)
    await state.set_state(BroadcastStates.waiting_content)
    await message.answer(
        "✍️ Отправьте текст объявления или одну фотографию "
        "с необязательной подписью.\n\n"
        "Сообщение начнёт рассылаться сразу после отправки.",
        reply_markup=cancel_broadcast_menu
    )


@router.message(
    BroadcastStates.waiting_content,
    F.media_group_id
)
async def broadcast_reject_album(message: Message, state: FSMContext):
    if not is_admin(message):
        return

    data = await state.get_data()

    if data.get("rejected_media_group_id") == message.media_group_id:
        return

    await state.update_data(rejected_media_group_id=message.media_group_id)
    await message.answer(
        "⚠️ Альбомы не поддерживаются. "
        "Отправьте одну фотографию или текст."
    )


@router.message(BroadcastStates.waiting_content)
async def broadcast_receive_content(message: Message, state: FSMContext):
    if not is_admin(message):
        return

    if not message.text and not message.photo:
        await message.answer(
            "⚠️ Поддерживается только текст или одна фотография "
            "с необязательной подписью."
        )
        return

    if broadcast_service.is_running:
        await state.clear()
        await message.answer(
            "⏳ Предыдущая рассылка уже выполняется. "
            "Попробуйте снова после итогового отчёта.",
            reply_markup=admin_menu
        )
        return

    data = await state.get_data()
    audience = BroadcastAudience(data["audience"])

    try:
        recipient_ids = await broadcast_service.resolve_recipients(audience)
    except AudienceLoadError as error:
        await message.answer(
            "❌ Не удалось получить данные получателей из 3X-UI.\n\n"
            f"Ошибка: {escape(str(error))}"
        )
        return

    if not recipient_ids:
        await state.clear()
        await message.answer(
            "ℹ️ В выбранной группе нет получателей.",
            reply_markup=admin_menu
        )
        return

    started = broadcast_service.start(
        bot=message.bot,
        admin_id=message.from_user.id,
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
        recipient_ids=recipient_ids
    )

    await state.clear()

    if not started:
        await message.answer(
            "⏳ Предыдущая рассылка уже выполняется.",
            reply_markup=admin_menu
        )
        return

    await message.answer(
        "🚀 <b>Рассылка запущена</b>\n\n"
        f"Получателей: <b>{len(recipient_ids)}</b>\n"
        "После завершения бот пришлёт итоговую статистику.",
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
