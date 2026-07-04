from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from keyboards.main_menu import main_menu

router = Router()

from aiogram.filters import CommandStart


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🌌 <b>Добро пожаловать в CosmoNet!</b>\n\n"
        "Выберите раздел:",
        reply_markup=main_menu
    )

subscription_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статус подписки")],
        [KeyboardButton(text="🛒 Купить / продлить")],
        [KeyboardButton(text="⬅️ Главное меню")]
    ],
    resize_keyboard=True
)


info_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔑 Как получить подписку")],
        [KeyboardButton(text="⚙️ Как подключить конфиг")],
        [KeyboardButton(text="📱 Какие приложения использовать")],
        [KeyboardButton(text="⬅️ Главное меню")]
    ],
    resize_keyboard=True
)


@router.message(F.text == "💳 Подписка")
async def subscription(message: Message):
    await message.answer(
        "💳 <b>Подписка</b>\n\n"
        "Здесь можно посмотреть статус подписки или купить/продлить доступ.",
        reply_markup=subscription_menu
    )


@router.message(F.text == "📊 Статус подписки")
async def subscription_status(message: Message):
    await message.answer(
        "📊 <b>Статус подписки</b>\n\n"
        "Статус: не активна\n"
        "Дата окончания: отсутствует"
    )


@router.message(F.text == "🛒 Купить / продлить")
async def buy_subscription(message: Message):
    await message.answer(
        "🛒 <b>Купить / продлить подписку</b>\n\n"
        "Скоро здесь будет выбор тарифа и оплата."
    )


@router.message(F.text == "ℹ️ INFO")
async def info(message: Message):
    await message.answer(
        "ℹ️ <b>INFO</b>\n\n"
        "Выберите нужный раздел:",
        reply_markup=info_menu
    )


@router.message(F.text == "🔑 Как получить подписку")
async def how_to_get_subscription(message: Message):
    await message.answer(
        "🔑 <b>Как получить подписку</b>\n\n"
        "1. Перейдите в раздел «Подписка».\n"
        "2. Нажмите «Купить / продлить».\n"
        "3. Выберите тариф.\n"
        "4. После оплаты бот выдаст VPN-конфиг."
    )


@router.message(F.text == "⚙️ Как подключить конфиг")
async def how_to_connect_config(message: Message):
    await message.answer(
        "⚙️ <b>Как подключить конфиг</b>\n\n"
        "1. Скопируйте или скачайте конфиг из бота.\n"
        "2. Откройте приложение для VPN.\n"
        "3. Нажмите «Добавить» или «Импорт».\n"
        "4. Вставьте конфиг.\n"
        "5. Нажмите «Подключиться»."
    )


@router.message(F.text == "📱 Какие приложения использовать")
async def apps(message: Message):
    await message.answer(
        "📱 <b>Какие приложения использовать</b>\n\n"
        "Android: v2rayNG, Hiddify, NekoBox\n"
        "iOS: Streisand, FoXray, Shadowrocket\n"
        "Windows: Hiddify, Nekoray\n"
        "macOS: Hiddify, FoXray"
    )


@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message):
    await message.answer(
        "🌌 Главное меню CosmoNet",
        reply_markup=main_menu
    )