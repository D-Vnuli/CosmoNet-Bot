from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str
    name: str
    devices: int
    emoji: str

    @property
    def devices_text(self) -> str:
        if self.devices == 1:
            return "1 устройство"

        return f"{self.devices} устройства"

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.name} — {self.devices_text}"


TARIFFS = (
    Tariff(code="lite", name="Lite", devices=1, emoji="🚀"),
    Tariff(code="standard", name="Standard", devices=3, emoji="⚡"),
    Tariff(code="family", name="Family", devices=5, emoji="👨‍👩‍👧‍👦"),
)


def get_tariff_by_button_text(button_text: str | None) -> Tariff | None:
    for tariff in TARIFFS:
        if tariff.button_text == button_text:
            return tariff

    return None
