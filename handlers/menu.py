from html import escape

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from services.subscription_service import SubscriptionService
from services.tariff_service import TARIFFS, get_tariff_by_button_text
from services.stars_payment_service import StarsPaymentService
from services.test_payment_service import TestPaymentService
from database import add_user_if_not_exists, is_registered_user
from keyboards.main_menu import main_menu
from services.xui_service import XUIService, format_bytes, format_expiry_time
from config import (
    ADMIN_IDS,
    PAY_SUPPORT_CONTACT,
    TEST_PAYMENTS_ENABLED,
    XUI_SUB_BASE_URL,
)

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


tariff_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=tariff.button_text)]
        for tariff in TARIFFS
    ] + [
        [KeyboardButton(text="⬅️ Назад к подписке")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите тариф"
)


def test_payment_keyboard(order_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🧪 Подтвердить тестовую оплату",
                callback_data=f"test_pay:{order_id}"
            )
        ]]
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


def can_use_test_payments(telegram_id: int) -> bool:
    return (
        telegram_id in ADMIN_IDS
        or TEST_PAYMENTS_ENABLED
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
            "После подключения оплаты текущая подписка будет продлена, "
            "а лимит устройств обновлён согласно тарифу."
        )
    else:
        action_text = (
            "После подключения оплаты бот создаст VPN-профиль "
            "с выбранным лимитом устройств."
        )

    payment_service = StarsPaymentService(service)
    stars_order = payment_service.create_order(
        telegram_id=message.from_user.id,
        tariff=tariff,
        purchase_result=result
    )

    reply_markup = tariff_menu
    test_payment_text = ""

    if (
        can_use_test_payments(message.from_user.id)
        and (
            message.from_user.id in ADMIN_IDS
            or is_registered_user(message.from_user.id)
        )
    ):
        payment_service = TestPaymentService(service)
        order = payment_service.create_order(
            telegram_id=message.from_user.id,
            tariff=tariff,
            purchase_result=result
        )
        reply_markup = test_payment_keyboard(order["id"])
        test_payment_text = (
            "\n\n🧪 <b>Тестовый режим:</b> деньги не списываются.\n"
            "Подтверждение изменит реальный профиль в 3X-UI."
        )

    await message.answer(
        f"{tariff.emoji} <b>Тариф {tariff.name}</b>\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Устройств:</b> {tariff.devices}\n"
        f"📅 <b>Срок:</b> {tariff.duration_days} дней\n"
        f"💰 <b>Стоимость:</b> {tariff.price_text} "
        f"или {tariff.stars_price_text} за 30 дней\n\n"
        f"{action_text}\n\n"
        "Ниже находится защищённый счёт Telegram Stars.\n"
        "Нажимая кнопку оплаты, вы принимаете /terms."
        f"{test_payment_text}",
        reply_markup=reply_markup
    )

    await message.answer_invoice(
        title=f"CosmoNet — тариф {tariff.name}",
        description=(
            f"VPN-подписка на {tariff.duration_days} дней, "
            f"устройств: {tariff.devices}. Оплата означает согласие "
            "с условиями /terms."
        ),
        payload=stars_order["invoice_payload"],
        currency="XTR",
        prices=[
            LabeledPrice(
                label=f"Тариф {tariff.name}",
                amount=tariff.price_stars
            )
        ],
        provider_token="",
        start_parameter=f"stars_{stars_order['id']}",
        protect_content=True
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


@router.callback_query(F.data.startswith("test_pay:"))
async def confirm_test_payment(callback: CallbackQuery):
    if not can_use_test_payments(callback.from_user.id):
        await callback.answer(
            "Тестовый режим оплаты отключён.",
            show_alert=True
        )
        return

    if (
        callback.from_user.id not in ADMIN_IDS
        and not is_registered_user(callback.from_user.id)
    ):
        await callback.answer(
            "Сначала запустите бота командой /start.",
            show_alert=True
        )
        return

    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (AttributeError, ValueError):
        await callback.answer("Некорректный тестовый заказ.", show_alert=True)
        return

    payment_service = TestPaymentService()
    order = payment_service.get_order(order_id)

    if not order or order["telegram_id"] != callback.from_user.id:
        await callback.answer("Тестовый заказ не найден.", show_alert=True)
        return

    await callback.answer("Обрабатываю тестовую оплату…")

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    result = await payment_service.confirm_order(order_id)

    if not callback.message:
        return

    if not result["success"]:
        retry_markup = (
            test_payment_keyboard(order_id)
            if result["status"] == "failed"
            else None
        )
        await callback.message.answer(
            "❌ <b>Тестовая оплата не завершена</b>\n\n"
            f"Ошибка: {escape(str(result['error']))}",
            reply_markup=retry_markup
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

    await callback.message.answer(
        "✅ <b>Тестовая оплата "
        f"{status_text}</b>\n\n"
        f"📦 Заказ: <code>#{order_id}</code>\n"
        f"📱 Устройств: <b>{result['order']['devices']}</b>\n"
        f"📅 Действует до: <b>{expiry_text}</b>"
        f"{config_text}",
        reply_markup=subscription_menu
    )


@router.message(F.text == "⬅️ Назад к подписке")
async def back_to_subscription(message: Message):
    await subscription(message)


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
