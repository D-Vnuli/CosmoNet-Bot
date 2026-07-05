from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str
    name: str
    devices: int
    duration_days: int
    price_rub: int
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


TARIFFS = (
    Tariff(
        code="lite",
        name="Lite",
        devices=1,
        duration_days=30,
        price_rub=129,
        emoji="🚀"
    ),
    Tariff(
        code="standard",
        name="Standard",
        devices=3,
        duration_days=30,
        price_rub=199,
        emoji="⚡"
    ),
    Tariff(
        code="family",
        name="Family",
        devices=5,
        duration_days=30,
        price_rub=279,
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
