from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from services.tariff_service import PAID_TARIFFS, TARIFFS


def build_tariff_menu(*, paid_only: bool = False) -> ReplyKeyboardMarkup:
    tariffs = PAID_TARIFFS if paid_only else TARIFFS
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tariff.button_text)]
            for tariff in tariffs
        ] + [[KeyboardButton(text="← В главное меню")]],
        resize_keyboard=True,
        input_field_placeholder="Выберите тариф",
    )
