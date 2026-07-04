from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from services.subscription_service import SubscriptionService
from database import add_user_if_not_exists
from keyboards.main_menu import main_menu
from services.xui_service import XUIService, format_bytes, format_expiry_time
from config import XUI_SUB_BASE_URL

router = Router()


subscription_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статус подписки")],
        [KeyboardButton(text="🔗 Получить конфиг")],
        [KeyboardButton(text="🛒 Купить / продлить")],
        [KeyboardButton(text="⬅️ Главное меню")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие"
)


info_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔑 Как получить подписку")],
        [KeyboardButton(text="⚙️ Как подключить конфиг")],
        [KeyboardButton(text="📱 Какие приложения использовать")],
        [KeyboardButton(text="⬅️ Главное меню")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите раздел"
)


@router.message(CommandStart())
async def start_handler(message: Message):
    add_user_if_not_exists(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        language_code=message.from_user.language_code
    )

    await message.answer(
        "🌌 <b>Добро пожаловать в CosmoNet</b>\n\n"
        "Быстрый, стабильный и удобный VPN-доступ без лишних настроек.\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "🚀 <b>Что доступно сейчас:</b>\n\n"
        "💳 Управление подпиской\n"
        "ℹ️ Информация по подключению\n"
        "📱 Рекомендации по приложениям\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Выберите нужный раздел ниже 👇",
        reply_markup=main_menu
    )


@router.message(F.text == "💳 Подписка")
async def subscription(message: Message):
    await message.answer(
        "💳 <b>Подписка CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Здесь можно посмотреть текущий статус подписки, "
        "а также купить или продлить доступ.\n\n"
        "Выберите действие ниже:",
        reply_markup=subscription_menu
    )


@router.message(F.text == "📊 Статус подписки")
async def subscription_status(message: Message):
    telegram_id = str(message.from_user.id)

    xui = XUIService()
    result = await xui.get_client_by_email(telegram_id)

    if not result["success"]:
        await message.answer(
            "📊 <b>Статус подписки</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "❌ Не удалось получить данные из 3X-UI.\n\n"
            f"Ошибка: {result['error']}"
        )
        return

    client = result["client"]

    if not client:
        await message.answer(
            "📊 <b>Статус подписки</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🔴 <b>Статус:</b> подписка не найдена\n\n"
            "Ваш профиль пока не связан с VPN-панелью.\n"
            "Обратитесь в поддержку."
        )
        return

    status_text = "🟢 активна" if client["enable"] else "🔴 отключена"
    expiry_text = format_expiry_time(client["expiry_time"])

    used_traffic = client["up"] + client["down"]
    used_text = format_bytes(used_traffic)

    devices_limit = client.get("limit_ip", 0)
    devices_text = "Без ограничения" if devices_limit == 0 else str(devices_limit)

    await message.answer(
        "📊 <b>Статус подписки CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"<b>Статус:</b> {status_text}\n"
        f"📅 <b>Действует до:</b> {expiry_text}\n"
        f"📊 <b>Использовано:</b> {used_text}\n"
        f"📱 <b>Устройств:</b> {devices_text}\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Спасибо, что пользуетесь CosmoNet 💚"
    )


@router.message(F.text == "🔗 Получить конфиг")
async def get_config(message: Message):
    telegram_id = str(message.from_user.id)

    xui = XUIService()
    result = await xui.get_client_by_email(telegram_id)

    if not result["success"]:
        await message.answer(
            "🔗 <b>Получить конфиг</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "❌ Не удалось получить данные из 3X-UI.\n\n"
            f"Ошибка: {result['error']}"
        )
        return

    client = result["client"]

    if not client:
        await message.answer(
            "🔗 <b>Получить конфиг</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🔴 VPN-конфиг не найден.\n\n"
            "Если вы уже оплатили подписку, обратитесь в поддержку."
        )
        return

    if not client["enable"]:
        await message.answer(
            "🔗 <b>Получить конфиг</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🔴 Ваша подписка отключена.\n\n"
            "Продлите доступ, чтобы снова использовать VPN."
        )
        return

    sub_id = client.get("sub_id")

    if not sub_id:
        await message.answer(
            "🔗 <b>Получить конфиг</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "❌ У пользователя не найден Sub ID в 3X-UI."
        )
        return

    base_url = XUI_SUB_BASE_URL.rstrip("/") if XUI_SUB_BASE_URL else ""

    if not base_url:
        await message.answer(
            "🔗 <b>Получить конфиг</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "❌ В .env не настроен XUI_SUB_BASE_URL."
        )
        return

    config_url = f"{base_url}/sub/{sub_id}"

    await message.answer(
        "🔗 <b>Ваш VPN-конфиг CosmoNet</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Скопируйте ссылку ниже и импортируйте её в приложение для VPN:\n\n"
        f"<code>{config_url}</code>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Не передавайте эту ссылку другим людям."
    )

@router.message(F.text == "🛒 Купить / продлить")
async def buy_subscription(message: Message):
    service = SubscriptionService()
    result = await service.get_purchase_action(message.from_user.id)

    if not result["success"]:
        await message.answer(
            "🛒 <b>Купить / продлить подписку</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "❌ Не удалось проверить данные в VPN-панели.\n\n"
            f"Ошибка: {result['error']}"
        )
        return

    if result["action"] == "renew":
        await message.answer(
            "🛒 <b>Продление подписки</b>\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "Ваш VPN-профиль уже найден в системе.\n\n"
            "Новый конфиг создаваться не будет.\n"
            "После оплаты будет продлена текущая подписка."
        )
        return

    await message.answer(
        "🛒 <b>Первая покупка подписки</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Ваш VPN-профиль пока не найден.\n\n"
        "После оплаты бот создаст новый VPN-конфиг и выдаст его вам."
    )


@router.message(F.text == "ℹ️ INFO")
async def info(message: Message):
    await message.answer(
        "ℹ️ <b>INFO</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Здесь собрана основная информация по использованию CosmoNet.\n\n"
        "Выберите нужный раздел:",
        reply_markup=info_menu
    )


@router.message(F.text == "🔑 Как получить подписку")
async def how_to_get_subscription(message: Message):
    await message.answer(
        "🔑 <b>Как получить подписку</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "1. Откройте раздел «💳 Подписка».\n"
        "2. Нажмите «🛒 Купить / продлить».\n"
        "3. Выберите подходящий тариф.\n"
        "4. Оплатите подписку.\n"
        "5. После оплаты бот выдаст VPN-конфиг.\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Автоматическая покупка будет добавлена позже."
    )


@router.message(F.text == "⚙️ Как подключить конфиг")
async def how_to_connect_config(message: Message):
    await message.answer(
        "⚙️ <b>Как подключить конфиг</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "1. Получите VPN-конфиг в боте.\n"
        "2. Установите подходящее приложение.\n"
        "3. Нажмите «Добавить» или «Импорт».\n"
        "4. Вставьте или импортируйте конфиг.\n"
        "5. Сохраните подключение.\n"
        "6. Нажмите «Подключиться».\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "После этого устройство будет подключено к CosmoNet."
    )


@router.message(F.text == "📱 Какие приложения использовать")
async def apps(message: Message):
    await message.answer(
        "📱 <b>Какие приложения использовать</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "🤖 <b>Android:</b>\n"
        "v2rayNG, Hiddify, NekoBox\n\n"
        "🍏 <b>iOS:</b>\n"
        "Streisand, FoXray, Shadowrocket\n\n"
        "🪟 <b>Windows:</b>\n"
        "Hiddify, Nekoray\n\n"
        "💻 <b>macOS:</b>\n"
        "Hiddify, FoXray\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Позже добавим подробные инструкции для каждой платформы."
    )


@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message):
    await message.answer(
        "🌌 <b>Главное меню CosmoNet</b>\n\n"
        "Выберите нужный раздел ниже:",
        reply_markup=main_menu
    )