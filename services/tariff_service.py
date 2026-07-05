from dataclasses import dataclass

from config import (
    STARS_PRICE_FAMILY,
    STARS_PRICE_LITE,
    STARS_PRICE_STANDARD,
)


@dataclass(frozen=True)
class Tariff:
    code: str
    name: str
    devices: int
    duration_days: int
    price_rub: int
    price_stars: int
    emoji: str

    @property
    def devices_text(self) -> str:
        if self.devices == 1:
            return "1 устройство"

        return f"{self.devices} устройства"

    @property
    def button_text(self) -> str:
        return (
            f"{self.emoji} {self.name} — "
            f"{self.devices_text} — {self.price_text}"
        )

    @property
    def price_text(self) -> str:
        return f"{self.price_rub} ₽"

    @property
    def stars_price_text(self) -> str:
        return f"{self.price_stars} ⭐"


TARIFFS = (
    Tariff(
        code="lite",
        name="Lite",
        devices=1,
        duration_days=30,
        price_rub=129,
        price_stars=STARS_PRICE_LITE,
        emoji="🚀"
    ),
    Tariff(
        code="standard",
        name="Standard",
        devices=3,
        duration_days=30,
        price_rub=199,
        price_stars=STARS_PRICE_STANDARD,
        emoji="⚡"
    ),
    Tariff(
        code="family",
        name="Family",
        devices=5,
        duration_days=30,
        price_rub=279,
        price_stars=STARS_PRICE_FAMILY,
        emoji="👨‍👩‍👧‍👦"
    ),
)


def get_tariff_by_button_text(button_text: str | None) -> Tariff | None:
    for tariff in TARIFFS:
        if tariff.button_text == button_text:
            return tariff

    return None


def get_tariff_by_code(code: str | None) -> Tariff | None:
    for tariff in TARIFFS:
        if tariff.code == code:
            return tariff

    return None
