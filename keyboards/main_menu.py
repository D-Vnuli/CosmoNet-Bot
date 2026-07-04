from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 Подписка")],
        [KeyboardButton(text="ℹ️ INFO")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите раздел"
)