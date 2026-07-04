from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from database import add_user_if_not_exists, get_user_with_subscription
from keyboards.main_menu import main_menu

router = Router()


subscription_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статус подписки")],
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
    user = get_user_with_subscription(message.from_user.id)

    if not user:
        await message.answer(
            "Пользователь не найден. Нажмите /start для регистрации."
        )
        return

    (
        user_id,
        telegram_id,
        username,
        first_name,
        last_name,
        language_code,
        registered_at,
        vpn_uuid,
        devices_count,
        last_connection,
        status,
        tariff,
        started_at,
        expires_at
    ) = user

    status_text = "🟢 активна" if status == "active" else "🔴 не активна"
    tariff_text = tariff if tariff else "отсутствует"
    expires_text = expires_at if expires_at else "—"

    await message.answer(
        "📊 <b>Статус подписки</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"<b>Статус:</b> {status_text}\n"
        f"📦 <b>Тариф:</b> {tariff_text}\n"
        f"📅 <b>Действует до:</b> {expires_text}\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Пользователь:</b> {first_name or '—'}\n"
        f"🆔 <b>Telegram ID:</b> {telegram_id}"
    )


@router.message(F.text == "🛒 Купить / продлить")
async def buy_subscription(message: Message):
    await message.answer(
        "🛒 <b>Купить / продлить подписку</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Скоро здесь появится выбор тарифа и автоматическая оплата.\n\n"
        "Пока бот находится в разработке."
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