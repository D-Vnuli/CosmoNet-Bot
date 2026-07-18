from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🚀 Подключиться"),
            KeyboardButton(text="🪐 Мой CosmoNet"),
        ],
        [
            KeyboardButton(text="🛰 Конфигурация"),
            KeyboardButton(text="🆘 Помощь"),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие",
)