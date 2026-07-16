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
    def __init__(self, data="test_pay:1", user_id=42):
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
                ("Lite", 1, 129),
                ("Standard", 3, 199),
                ("Family", 5, 279),
                ("Promo", 1, 50)
            ]
        )

        for tariff in TARIFFS:
            self.assertIs(
                get_tariff_by_button_text(tariff.button_text),
                tariff
            )
            self.assertIn(tariff.price_text, tariff.button_text)

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
        tariff = TARIFFS[1]
        message = FakeMessage(text=tariff.button_text)
        service = Mock()
        service.get_purchase_action = AsyncMock(return_value={
            "success": True,
            "action": "renew",
            "error": None,
            "client": {"enable": True}
        })

        with (
            patch.object(menu, "TEST_PAYMENTS_ENABLED", False),
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
        buttons = kwargs["reply_markup"].inline_keyboard[0]
        self.assertEqual(
            [button.callback_data for button in buttons],
            ["pay_stars:standard", "pay_card:standard"]
        )
        self.assertEqual(message.invoices, [])

    async def test_registered_user_can_create_test_order(self):
        tariff = TARIFFS[2]
        message = FakeMessage(text=tariff.button_text, user_id=99)
        subscription_service = Mock()
        subscription_service.get_purchase_action = AsyncMock(return_value={
            "success": True,
            "action": "create",
            "error": None,
            "client": None
        })
        payment_service = Mock()
        payment_service.create_order = Mock(return_value={"id": 31})

        with (
            patch.object(menu, "ADMIN_IDS", [42]),
            patch.object(menu, "TEST_PAYMENTS_ENABLED", True),
            patch.object(menu, "is_registered_user", return_value=True),
            patch.object(
                menu,
                "SubscriptionService",
                return_value=subscription_service
            ),
            patch.object(
                menu,
                "TestPaymentService",
                return_value=payment_service
            )
        ):
            await menu.select_tariff(message)

        text, kwargs = message.answers[0]
        button = kwargs["reply_markup"].inline_keyboard[1][0]
        self.assertIn("доступна тестовая оплата", text)
        self.assertEqual(button.callback_data, "test_pay:31")

    async def test_registered_user_can_confirm_own_test_order(self):
        callback = FakeCallback(data="test_pay:31", user_id=99)
        payment_service = Mock()
        payment_service.get_order = Mock(return_value={
            "id": 31,
            "telegram_id": 99,
            "devices": 5,
            "status": "pending"
        })
        payment_service.confirm_order = AsyncMock(return_value={
            "success": True,
            "status": "paid",
            "error": None,
            "order": {
                "id": 31,
                "telegram_id": 99,
                "devices": 5,
                "status": "paid"
            },
            "client": {
                "sub_id": "sub-31",
                "expiry_time": 1_900_000_000_000
            }
        })

        with (
            patch.object(menu, "ADMIN_IDS", [42]),
            patch.object(menu, "TEST_PAYMENTS_ENABLED", True),
            patch.object(menu, "is_registered_user", return_value=True),
            patch.object(menu, "XUI_SUB_BASE_URL", "https://vpn.example"),
            patch.object(
                menu,
                "TestPaymentService",
                return_value=payment_service
            )
        ):
            await menu.confirm_test_payment(callback)

        payment_service.confirm_order.assert_awaited_once_with(31)
        confirmation = callback.message.answer.await_args.args[0]
        self.assertIn("успешно подтверждена", confirmation)

    async def test_admin_tariff_selection_creates_test_order_button(self):
        tariff = TARIFFS[0]
        message = FakeMessage(text=tariff.button_text)
        subscription_service = Mock()
        subscription_service.get_purchase_action = AsyncMock(return_value={
            "success": True,
            "action": "create",
            "error": None,
            "client": None
        })
        payment_service = Mock()
        payment_service.create_order = Mock(return_value={"id": 17})

        with (
            patch.object(menu, "ADMIN_IDS", [42]),
            patch.object(menu, "is_registered_user", return_value=True),
            patch.object(
                menu,
                "SubscriptionService",
                return_value=subscription_service
            ),
            patch.object(
                menu,
                "TestPaymentService",
                return_value=payment_service
            )
        ):
            await menu.select_tariff(message)

        text, kwargs = message.answers[0]
        button = kwargs["reply_markup"].inline_keyboard[1][0]
        self.assertIn("доступна тестовая оплата", text)
        self.assertEqual(button.callback_data, "test_pay:17")

    async def test_admin_can_confirm_test_order(self):
        callback = FakeCallback(data="test_pay:17")
        payment_service = Mock()
        payment_service.get_order = Mock(return_value={
            "id": 17,
            "telegram_id": 42,
            "devices": 3,
            "status": "pending"
        })
        payment_service.confirm_order = AsyncMock(return_value={
            "success": True,
            "status": "paid",
            "error": None,
            "order": {
                "id": 17,
                "telegram_id": 42,
                "devices": 3,
                "status": "paid"
            },
            "client": {
                "sub_id": "sub-17",
                "expiry_time": 1_900_000_000_000
            }
        })

        with (
            patch.object(menu, "ADMIN_IDS", [42]),
            patch.object(menu, "XUI_SUB_BASE_URL", "https://vpn.example"),
            patch.object(
                menu,
                "TestPaymentService",
                return_value=payment_service
            )
        ):
            await menu.confirm_test_payment(callback)

        payment_service.confirm_order.assert_awaited_once_with(17)
        callback.message.edit_reply_markup.assert_awaited_once_with(
            reply_markup=None
        )
        confirmation = callback.message.answer.await_args.args[0]
        self.assertIn("успешно подтверждена", confirmation)
        self.assertIn(
            "https://vpn.example/sub/sub-17",
            confirmation
        )


if __name__ == "__main__":
    unittest.main()
