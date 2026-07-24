from html import escape
from pathlib import Path

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from services.subscription_service import SubscriptionService
from services.tariff_service import (
    TARIFFS,
    get_tariff_by_button_text,
    get_tariff_by_code,
    get_tariff_for_user,
)
from services.stars_payment_service import StarsPaymentService
from services.yookassa_payment_service import YooKassaPaymentService
from database import add_user_if_not_exists, is_registered_user
from keyboards.main_menu import main_menu
from services.xui_service import XUIService, format_bytes, format_expiry_time
from config import (
    ADMIN_IDS,
    PAY_SUPPORT_CONTACT,
    XUI_SUB_BASE_URL,
)

router = Router()

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
WELCOME_BANNER = ASSETS_DIR / "cosmonet-orbit.png"


def _ru(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


class FeedbackStates(StatesGroup):
    waiting_message = State()


subscription_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📡 Статус")],
        [KeyboardButton(text="🛰 Конфигурация")],
        [KeyboardButton(text="← В главное меню")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Управляйте подпиской",
)

info_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔐 Как подключиться")],
        [KeyboardButton(text="📱 Приложения"), KeyboardButton(text="💬 Поддержка")],
        [KeyboardButton(text="← В главное меню")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Полезная информация",
)

tariff_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=tariff.button_text)]
        for tariff in TARIFFS
    ] + [[KeyboardButton(text="← В главное меню")]],
    resize_keyboard=True,
    input_field_placeholder="Выберите тариф",
)

feedback_cancel_menu = ReplyKeyboardMarkup(
    keyboard=[[
        KeyboardButton(text="❌ Отменить обращение")
    ]],
    resize_keyboard=True,
    input_field_placeholder="Напишите сообщение или отправьте скриншот"
)


def payment_method_keyboard(tariff_code: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Карта или СБП", callback_data=f"pay_card:{tariff_code}")],
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_stars:{tariff_code}")],
            [InlineKeyboardButton(text="📄 Условия и возвраты", url="https://cosmonet.shop/documents/offer.html")],
        ]
    )
def stars_retry_keyboard(order_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🔄 Повторить выдачу подписки",
                callback_data=f"stars_retry:{order_id}"
            )
        ]]
    )


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    add_user_if_not_exists(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        language_code=message.from_user.language_code,
    )

    caption = (
        "<b>CosmoNet</b>  ·  личная орбита связи\n\n"
        "Защищённый доступ, понятные тарифы и управление подпиской "
        "в одном месте.\n\n"
        "<i>Выберите действие в меню ниже.</i>"
    )
    if WELCOME_BANNER.exists():
        await message.answer_photo(
            photo=FSInputFile(WELCOME_BANNER),
            caption=caption,
            reply_markup=main_menu,
        )
    else:
        await message.answer(caption, reply_markup=main_menu)

@router.message(Command("paysupport"))
async def payment_support(message: Message):
    if PAY_SUPPORT_CONTACT:
        contact_text = escape(PAY_SUPPORT_CONTACT)
    elif ADMIN_IDS:
        contact_text = (
            f'<a href="tg://user?id={ADMIN_IDS[0]}">'
            "администратор CosmoNet</a>"
        )
    else:
        contact_text = "контакт пока не настроен"

    await message.answer(
        "🛟 <b>Поддержка по платежам</b>\n\n"
        "Опишите проблему и обязательно укажите номер заказа "
        "из сообщения об оплате.\n\n"
        f"Контакт поддержки: {contact_text}"
    )


@router.message(Command("terms"))
async def payment_terms(message: Message):
    await message.answer(
        "📄 <b>Условия покупки подписки CosmoNet</b>\n\n"
        "1. Подписка предоставляет VPN-доступ на 30 дней с лимитом "
        "устройств выбранного тарифа.\n"
        "2. Доступ создаётся или продлевается сразу после подтверждения "
        "платежа Telegram.\n"
        "3. Пользователь обязуется соблюдать применимое законодательство "
        "и не использовать сервис для противоправных действий.\n"
        "4. При технической ошибке доступ будет восстановлен либо вопрос "
        "будет решён через поддержку.\n"
        "5. По вопросам оплаты используйте /paysupport. Telegram не "
        "является продавцом услуги и не обрабатывает обращения по покупке.\n\n"
        "Нажимая кнопку оплаты, пользователь подтверждает, что прочитал "
        "и принимает эти условия."
    )


@router.message(F.text.in_({"💬 Обратная связь", "💬 Поддержка"}))
async def feedback_start(message: Message, state: FSMContext):
    await state.set_state(FeedbackStates.waiting_message)
    await message.answer(
        "💬 <b>Обратная связь</b>\n\n"
        "Одним сообщением опишите вопрос, предложение или проблему. "
        "Можно отправить текст либо один скриншот с подписью.\n\n"
        "Администратор увидит ваш Telegram-аккаунт и сможет связаться "
        "с вами.",
        reply_markup=feedback_cancel_menu
    )


@router.message(
    FeedbackStates.waiting_message,
    Command("cancel")
)
@router.message(
    FeedbackStates.waiting_message,
    F.text == "❌ Отменить обращение"
)
async def feedback_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Обращение отменено.",
        reply_markup=info_menu
    )


@router.message(
    FeedbackStates.waiting_message,
    F.media_group_id
)
async def feedback_reject_album(message: Message):
    await message.answer(
        "Отправьте только один скриншот, не альбом."
    )


@router.message(
    FeedbackStates.waiting_message,
    F.text | F.photo
)
async def feedback_receive(message: Message, state: FSMContext):
    if not ADMIN_IDS:
        await message.answer(
            "Сейчас обратная связь недоступна: "
            "контакт администратора не настроен."
        )
        return

    user = message.from_user
    username = (
        f"@{escape(user.username)}"
        if user.username
        else "не указан"
    )
    full_name = escape(user.full_name or "Без имени")
    profile_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="👤 Открыть профиль",
                url=f"tg://user?id={user.id}"
            )
        ]]
    )
    header = (
        "💬 <b>Новое обращение CosmoNet</b>\n\n"
        f"👤 <b>Пользователь:</b> "
        f'<a href="tg://user?id={user.id}">{full_name}</a>\n'
        f"🔹 <b>Username:</b> {username}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n\n"
        "Сообщение пользователя ниже:"
    )
    delivered = 0

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                chat_id=admin_id,
                text=header,
                reply_markup=profile_keyboard
            )
            await message.copy_to(chat_id=admin_id)
            delivered += 1
        except TelegramAPIError:
            continue

    if delivered == 0:
        await message.answer(
            "Не удалось передать обращение. Попробуйте немного позже."
        )
        return

    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено администратору.\n\n"
        "Спасибо за обратную связь!",
        reply_markup=info_menu
    )


@router.message(FeedbackStates.waiting_message)
async def feedback_reject_content(message: Message):
    await message.answer(
        "Поддерживается текст или один скриншот с подписью."
    )


@router.message(F.text == "🪐 Мой CosmoNet")
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


@router.message(F.text == "📡 Статус")
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


@router.message(F.text == "🛰 Конфигурация")
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

@router.message(F.text.in_({"🛒 Тарифы", "🚀 Подключиться"}))
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
            "После оплаты будет продлена текущая подписка.\n\n"
            "Выберите тариф:",
            reply_markup=tariff_menu
        )
        return

    await message.answer(
        "🛒 <b>Первая покупка подписки</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "Ваш VPN-профиль пока не найден.\n\n"
        "После оплаты бот создаст новый VPN-конфиг и выдаст его вам.\n\n"
        "Выберите тариф:",
        reply_markup=tariff_menu
    )


@router.message(F.text.in_({
    tariff.button_text
    for tariff in TARIFFS
}))
async def select_tariff(message: Message):
    tariff = get_tariff_by_button_text(message.text)

    if not tariff:
        return

    tariff = get_tariff_for_user(message.from_user.id, tariff)

    if not is_registered_user(message.from_user.id):
        await message.answer(
            "Сначала зарегистрируйтесь в боте командой /start."
        )
        return

    service = SubscriptionService()
    result = await service.get_purchase_action(message.from_user.id)

    if not result["success"]:
        await message.answer(
            "❌ Не удалось проверить данные в VPN-панели.\n\n"
            f"Ошибка: {result['error']}"
        )
        return

    if result["action"] == "renew":
        action_text = (
            "После оплаты текущая подписка будет продлена, "
            "а лимит устройств обновлён согласно тарифу."
        )
    else:
        action_text = (
            "После оплаты бот создаст VPN-профиль "
            "с выбранным лимитом устройств."
        )

    await message.answer(
        f"{tariff.emoji} <b>Тариф {tariff.name}</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Устройств:</b> {tariff.devices}\n"
        f"📅 <b>Срок:</b> {tariff.duration_days} дней\n"
        f"💰 <b>Стоимость:</b> {tariff.price_text} за {tariff.duration_days} дней\n\n"
        f"{action_text}\n\n"
        "Выберите способ оплаты:",
        reply_markup=payment_method_keyboard(tariff.code)
    )


@router.callback_query(F.data.startswith("pay_stars:"))
async def select_stars_payment(callback: CallbackQuery):
    tariff_code = callback.data.split(":", 1)[1]
    tariff = get_tariff_by_code(tariff_code)

    if not tariff:
        await callback.answer(
            "Тариф не найден.",
            show_alert=True
        )
        return

    tariff = get_tariff_for_user(callback.from_user.id, tariff)

    if not is_registered_user(callback.from_user.id):
        await callback.answer(
            "Сначала запустите бота командой /start.",
            show_alert=True
        )
        return

    service = SubscriptionService()
    purchase_result = await service.get_purchase_action(
        callback.from_user.id
    )

    if not purchase_result["success"]:
        await callback.answer(
            "Не удалось проверить VPN-профиль.",
            show_alert=True
        )
        return

    payment_service = StarsPaymentService(service)
    order = payment_service.create_order(
        telegram_id=callback.from_user.id,
        tariff=tariff,
        purchase_result=purchase_result
    )

    await callback.answer()

    if not callback.message:
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"⭐ <b>Оплата Telegram Stars</b>\n\n"
        f"{tariff.emoji} Тариф: <b>{tariff.name}</b>\n"
        f"📱 Устройств: <b>{tariff.devices}</b>\n"
        f"📅 Срок: <b>{tariff.duration_days} дней</b>\n"
        f"⭐ К оплате: <b>{tariff.stars_price_text}</b>\n\n"
        "Нажимая кнопку оплаты в счёте ниже, "
        "вы принимаете /terms."
    )
    await callback.message.answer_invoice(
        title=f"CosmoNet — тариф {tariff.name}",
        description=(
            f"VPN-подписка на {tariff.duration_days} дней, "
            f"устройств: {tariff.devices}. Оплата означает согласие "
            "с условиями /terms."
        ),
        payload=order["invoice_payload"],
        currency="XTR",
        prices=[
            LabeledPrice(
                label=f"Тариф {tariff.name}",
                amount=tariff.price_stars
            )
        ],
        provider_token="",
        start_parameter=f"stars_{order['id']}",
        protect_content=True
    )


@router.callback_query(F.data.startswith("pay_card:"))
async def select_card_payment(callback: CallbackQuery):
    tariff_code = callback.data.split(":", 1)[1]
    tariff = get_tariff_by_code(tariff_code)

    if not tariff:
        await callback.answer(_ru(r"\u0422\u0430\u0440\u0438\u0444 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d."), show_alert=True)
        return

    tariff = get_tariff_for_user(callback.from_user.id, tariff)
    if not is_registered_user(callback.from_user.id):
        await callback.answer(_ru(r"\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u0431\u043e\u0442 \u043a\u043e\u043c\u0430\u043d\u0434\u043e\u0439 /start."), show_alert=True)
        return

    subscription_service = SubscriptionService()
    purchase_result = await subscription_service.get_purchase_action(callback.from_user.id)
    if not purchase_result["success"]:
        await callback.answer(_ru(r"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c VPN-\u043f\u0440\u043e\u0444\u0438\u043b\u044c."), show_alert=True)
        return

    payment_service = YooKassaPaymentService(subscription_service)
    if not payment_service.is_configured:
        await callback.answer(_ru(r"\u041e\u043f\u043b\u0430\u0442\u0430 \u043a\u0430\u0440\u0442\u043e\u0439 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430."), show_alert=True)
        return

    order = payment_service.create_order(telegram_id=callback.from_user.id, tariff=tariff, purchase_result=purchase_result)
    try:
        payment_url = await payment_service.create_payment(order)
    except RuntimeError:
        await callback.answer(_ru(r"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u043b\u0430\u0442\u0451\u0436. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435."), show_alert=True)
        return

    await callback.answer()
    if not callback.message:
        return

    await callback.message.edit_text(
        _ru(r"\U0001f4b3 <b>\u041e\u043f\u043b\u0430\u0442\u0430 \u043a\u0430\u0440\u0442\u043e\u0439 \u0438\u043b\u0438 \u0421\u0411\u041f</b>\n\n")
        + f"{tariff.emoji} " + _ru(r"\u0422\u0430\u0440\u0438\u0444: ") + f"<b>{tariff.name}</b>\n"
        + _ru(r"\U0001f4f1 \u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430: ") + f"<b>{tariff.devices}</b>\n"
        + _ru(r"\U0001f4c5 \u0421\u0440\u043e\u043a: ") + f"<b>{tariff.duration_days}</b> " + _ru(r"\u0434\u043d\u0435\u0439\n")
        + _ru(r"\U0001f4b3 \u041a \u043e\u043f\u043b\u0430\u0442\u0435: ") + f"<b>{tariff.price_text}</b>\n\n"
        + _ru(r"\u0412\u044b \u0431\u0443\u0434\u0435\u0442\u0435 \u043f\u0435\u0440\u0435\u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u044b \u0432 YooKassa. \u041f\u043e\u0441\u043b\u0435 \u0443\u0441\u043f\u0435\u0448\u043d\u043e\u0439 \u043e\u043f\u043b\u0430\u0442\u044b \u0431\u043e\u0442 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0432\u044b\u0434\u0430\u0441\u0442 \u0438\u043b\u0438 \u043f\u0440\u043e\u0434\u043b\u0438\u0442 \u0434\u043e\u0441\u0442\u0443\u043f."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=_ru(r"\U0001f4b3 \u041f\u0435\u0440\u0435\u0439\u0442\u0438 \u043a \u043e\u043f\u043b\u0430\u0442\u0435"), url=payment_url)
        ]]),
    )

@router.pre_checkout_query()
async def process_stars_pre_checkout(query: PreCheckoutQuery):
    service = StarsPaymentService()
    is_valid, error = service.validate_checkout(
        telegram_id=query.from_user.id,
        payload=query.invoice_payload,
        currency=query.currency,
        total_amount=query.total_amount
    )

    await query.answer(
        ok=is_valid,
        error_message=error
    )


@router.message(F.successful_payment)
async def process_successful_stars_payment(message: Message):
    payment = message.successful_payment

    if not payment or payment.currency != "XTR":
        return

    service = StarsPaymentService()
    result = await service.process_payment(
        telegram_id=message.from_user.id,
        payload=payment.invoice_payload,
        currency=payment.currency,
        total_amount=payment.total_amount,
        telegram_payment_charge_id=(
            payment.telegram_payment_charge_id
        ),
        provider_payment_charge_id=(
            payment.provider_payment_charge_id
        )
    )

    await send_stars_payment_result(message, result)


@router.callback_query(F.data.startswith("stars_retry:"))
async def retry_stars_provisioning(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (AttributeError, ValueError):
        await callback.answer(
            "Некорректный номер заказа.",
            show_alert=True
        )
        return

    await callback.answer("Повторяю выдачу подписки…")

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    service = StarsPaymentService()
    result = await service.retry_provisioning(
        order_id=order_id,
        telegram_id=callback.from_user.id
    )

    if callback.message:
        await send_stars_payment_result(callback.message, result)


async def send_stars_payment_result(message: Message, result: dict):
    order = result.get("order")

    if not result["success"]:
        if result["status"] == "provisioning_failed" and order:
            await message.answer(
                "⚠️ <b>Оплата получена, но подписка пока не выдана</b>\n\n"
                f"📦 Заказ: <code>#{order['id']}</code>\n"
                f"⭐ Получено: <b>{order['payment_amount']}</b>\n\n"
                "Повторно оплачивать тариф не нужно. "
                "Попробуйте повторить выдачу или обратитесь в поддержку.\n\n"
                f"Техническая ошибка: "
                f"{escape(str(result['error']))}",
                reply_markup=stars_retry_keyboard(order["id"])
            )
            return

        await message.answer(
            "⚠️ <b>Платёж получен и обрабатывается</b>\n\n"
            "Не оплачивайте тариф повторно. Если подписка не появится, "
            "обратитесь в поддержку через /paysupport."
        )
        return

    client = result["client"]
    sub_id = client.get("sub_id") if client else None
    expiry_text = (
        format_expiry_time(client.get("expiry_time"))
        if client
        else "—"
    )
    config_url = None

    if XUI_SUB_BASE_URL and sub_id:
        config_url = (
            f"{XUI_SUB_BASE_URL.rstrip('/')}/sub/{sub_id}"
        )

    config_text = (
        f"\n\n🔗 <b>VPN-конфиг:</b>\n<code>{config_url}</code>"
        if config_url
        else "\n\n⚠️ Ссылка конфигурации пока недоступна."
    )
    status_text = (
        "уже была обработана"
        if result["status"] == "already_paid"
        else "успешно подтверждена"
    )

    await message.answer(
        f"✅ <b>Оплата Telegram Stars {status_text}</b>\n\n"
        f"📦 Заказ: <code>#{order['id']}</code>\n"
        f"⭐ Оплачено: <b>{order['payment_amount']}</b>\n"
        f"📱 Устройств: <b>{order['devices']}</b>\n"
        f"📅 Действует до: <b>{expiry_text}</b>"
        f"{config_text}",
        reply_markup=subscription_menu
    )


@router.message(F.text == "← К подписке")
@router.message(F.text == "⬅️ Назад к подписке")
async def back_to_subscription(message: Message):
    await subscription(message)


@router.message(F.text.in_({"ℹ️ INFO", "🆘 Помощь"}))
async def info(message: Message):
    await message.answer(
        "🆘 <b>Помощь CosmoNet</b>\n\n"
        "Выберите нужный раздел:\n"
        "🔐 Как подключиться — от тарифа до первого соединения.\n"
        "📱 Приложения — CosmoNet для Windows.\n"
        "💬 Поддержка — вопрос по оплате или доступу.",
        reply_markup=info_menu
    )

@router.message(F.text.in_({"🔑 Как получить подписку", "🔐 Как подключиться"}))
async def how_to_get_subscription(message: Message):
    await message.answer(
        "🔐 <b>Как подключиться</b>\n\n"
        "<b>Android и iPhone</b>\n"
        "1. Выберите приложение в разделе «📱 Приложения».\n"
        "2. В боте откройте «🛰 Конфигурация» и скопируйте личную ссылку.\n"
        "3. В приложении выберите импорт ссылки/подписки из буфера и включите VPN.\n\n"
        "<b>Windows</b>\n"
        "1. Установите CosmoNet для Windows.\n"
        "2. Нажмите «Войти через Telegram» и подтвердите вход в боте.\n"
        "3. Подписка и профиль подтянутся автоматически — ссылку конфигурации вставлять не нужно."
    )

@router.message(F.text == "⚙️ Как подключить конфиг")
async def how_to_connect_config(message: Message):
    await message.answer(
        "⚙️ <b>Как подключить VPN</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "1. Установите приложение из раздела "
        "«📱 Какие приложения использовать».\n"
        "2. Откройте «💳 Подписка» → «🔗 Получить конфиг».\n"
        "3. Нажмите на ссылку конфига, чтобы скопировать её.\n"
        "4. В приложении выберите «Добавить из буфера» "
        "или «Импортировать ссылку».\n"
        "5. Разрешите создание VPN-подключения и нажмите кнопку запуска.\n\n"
        "Не передавайте ссылку конфига другим людям."
    )


@router.message(F.text.in_({"📱 Какие приложения использовать", "📱 Приложения"}))
async def apps(message: Message):
    await message.answer(
        "📱 <b>Приложения для подключения</b>\n\n"
        "<b>Android</b>\n"
        "• v2RayTun\n"
        "• Hiddify\n"
        "• v2rayNG\n"
        "• NekoBox\n\n"
        "<b>iPhone и iPad</b>\n"
        "• Happ\n"
        "• Streisand\n"
        "• Hiddify\n"
        "• Shadowrocket\n\n"
        "<b>Windows</b>\n"
        "• CosmoNet для Windows\n\n"
        "Мобильные приложения устанавливайте из Google Play или App Store. "
        "Доступность некоторых приложений на iPhone зависит от региона Apple Account."
    )

@router.message(F.text == "← В главное меню")
@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message):
    await message.answer(
        "🌌 <b>Главное меню CosmoNet</b>\n\n"
        "Выберите нужный раздел ниже:",
        reply_markup=main_menu
    )
