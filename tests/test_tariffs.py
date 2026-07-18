import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from handlers import admin, menu
from services.tariff_service import TARIFFS, get_tariff_by_button_text


class FakeMessage:
    def __init__(self, text=None, user_id=42):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.invoices = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def answer_invoice(self, **kwargs):
        self.invoices.append(kwargs)


class FakeCallback:
    def __init__(self, data="", user_id=42):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.message = Mock()
        self.message.edit_reply_markup = AsyncMock()
        self.message.answer = AsyncMock()
        self.message.answer_invoice = AsyncMock()

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class TariffTests(unittest.IsolatedAsyncioTestCase):
    def test_tariff_catalog_contains_expected_devices_and_prices(self):
        self.assertEqual(
            [
                (tariff.name, tariff.devices, tariff.price_rub)
                for tariff in TARIFFS
            ],
            [
                ("Demo", 1, 50),
                ("Lite", 1, 129),
                ("Standard", 3, 199),
                ("Family", 5, 279)
            ]
        )

        for tariff in TARIFFS:
            self.assertIs(
                get_tariff_by_button_text(tariff.button_text),
                tariff
            )
            self.assertIn(tariff.price_text, tariff.button_text)
            self.assertIn(f"{tariff.duration_days} дней", tariff.button_text)

    def test_admin_buttons_do_not_repeat_admin_label(self):
        button_texts = [
            button.text
            for row in admin.admin_menu.keyboard
            for button in row
        ]

        self.assertIn("📊 Статистика", button_texts)
        self.assertIn("👥 Пользователи", button_texts)
        self.assertFalse(any("Админ:" in text for text in button_texts))

    async def test_purchase_action_shows_tariff_menu(self):
        message = FakeMessage(text="🛒 Купить / продлить")
        service = Mock()
        service.get_purchase_action = AsyncMock(return_value={
            "success": True,
            "action": "create",
            "error": None,
            "client": None
        })

        with patch.object(
            menu,
            "SubscriptionService",
            return_value=service
        ):
            await menu.buy_subscription(message)

        text, kwargs = message.answers[0]
        self.assertIn("Первая покупка подписки", text)
        self.assertIn("Выберите тариф", text)
        self.assertIs(kwargs["reply_markup"], menu.tariff_menu)

    async def test_select_tariff_shows_devices_and_monthly_price(self):
        tariff = TARIFFS[2]
        message = FakeMessage(text=tariff.button_text)
        service = Mock()
        service.get_purchase_action = AsyncMock(return_value={
            "success": True,
            "action": "renew",
            "error": None,
            "client": {"enable": True}
        })

        with (
            patch.object(menu, "is_registered_user", return_value=True),
            patch.object(
                menu,
                "SubscriptionService",
                return_value=service
            )
        ):
            await menu.select_tariff(message)

        text, kwargs = message.answers[0]
        self.assertIn("Тариф Standard", text)
        self.assertIn("Устройств:</b> 3", text)
        self.assertIn("Стоимость:</b> 199 ₽", text)
        self.assertIn("Выберите способ оплаты", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in buttons[:2]],
            ["pay_card:standard", "pay_stars:standard"]
        )
        self.assertEqual(message.invoices, [])

if __name__ == "__main__":
    unittest.main()
