import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import database
from handlers import menu
from services.stars_payment_service import StarsPaymentService
from services.tariff_service import TARIFFS


class StarsPaymentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patcher = patch.object(
            database,
            "DB_PATH",
            Path(self.temp_dir.name) / "test.db"
        )
        self.db_path_patcher.start()
        database.init_db()

    def tearDown(self):
        self.db_path_patcher.stop()
        self.temp_dir.cleanup()

    def create_service_and_order(self):
        subscription_service = Mock()
        service = StarsPaymentService(subscription_service)
        order = service.create_order(
            telegram_id=1001,
            tariff=TARIFFS[0],
            purchase_result={
                "action": "create",
                "client": None
            }
        )
        return service, subscription_service, order

    def test_checkout_validates_user_amount_currency_and_status(self):
        service, _, order = self.create_service_and_order()

        valid, error = service.validate_checkout(
            telegram_id=1001,
            payload=order["invoice_payload"],
            currency="XTR",
            total_amount=TARIFFS[0].price_stars
        )
        wrong_amount, _ = service.validate_checkout(
            telegram_id=1001,
            payload=order["invoice_payload"],
            currency="XTR",
            total_amount=TARIFFS[0].price_stars + 1
        )
        wrong_user, _ = service.validate_checkout(
            telegram_id=2002,
            payload=order["invoice_payload"],
            currency="XTR",
            total_amount=TARIFFS[0].price_stars
        )

        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertFalse(wrong_amount)
        self.assertFalse(wrong_user)

    async def test_successful_payment_provisions_only_once(self):
        service, subscription_service, order = (
            self.create_service_and_order()
        )
        subscription_service.provision_subscription = AsyncMock(
            return_value={
                "success": True,
                "error": None,
                "client": {
                    "email": "1001",
                    "sub_id": "sub-1",
                    "expiry_time": order["target_expiry_ms"]
                }
            }
        )
        subscription_service.get_user_vpn_client = AsyncMock(
            return_value={
                "success": True,
                "error": None,
                "client": {
                    "email": "1001",
                    "sub_id": "sub-1"
                }
            }
        )
        payment = {
            "telegram_id": 1001,
            "payload": order["invoice_payload"],
            "currency": "XTR",
            "total_amount": TARIFFS[0].price_stars,
            "telegram_payment_charge_id": "tg-charge-1",
            "provider_payment_charge_id": ""
        }

        first = await service.process_payment(**payment)
        second = await service.process_payment(**payment)

        self.assertTrue(first["success"])
        self.assertEqual(first["order"]["status"], "paid")
        self.assertEqual(
            first["order"]["telegram_payment_charge_id"],
            "tg-charge-1"
        )
        self.assertEqual(second["status"], "already_paid")
        subscription_service.provision_subscription.assert_awaited_once()

    async def test_failed_provision_can_retry_without_second_payment(self):
        service, subscription_service, order = (
            self.create_service_and_order()
        )
        subscription_service.provision_subscription = AsyncMock(
            side_effect=[
                {
                    "success": False,
                    "error": "3X-UI unavailable",
                    "client": None
                },
                {
                    "success": True,
                    "error": None,
                    "client": {
                        "email": "1001",
                        "sub_id": "sub-1"
                    }
                }
            ]
        )

        first = await service.process_payment(
            telegram_id=1001,
            payload=order["invoice_payload"],
            currency="XTR",
            total_amount=TARIFFS[0].price_stars,
            telegram_payment_charge_id="tg-charge-2",
            provider_payment_charge_id=""
        )
        second = await service.retry_provisioning(
            order_id=order["id"],
            telegram_id=1001
        )

        self.assertEqual(first["status"], "provisioning_failed")
        self.assertTrue(second["success"])
        self.assertEqual(second["order"]["status"], "paid")
        self.assertEqual(
            subscription_service.provision_subscription.await_count,
            2
        )


class StarsPaymentHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stars_invoice_is_created_after_method_selection(self):
        callback = Mock()
        callback.data = "pay_stars:standard"
        callback.from_user = SimpleNamespace(id=1001)
        callback.answer = AsyncMock()
        callback.message = Mock()
        callback.message.edit_reply_markup = AsyncMock()
        callback.message.answer = AsyncMock()
        callback.message.answer_invoice = AsyncMock()
        subscription_service = Mock()
        subscription_service.get_purchase_action = AsyncMock(
            return_value={
                "success": True,
                "action": "create",
                "error": None,
                "client": None
            }
        )
        stars_service = Mock()
        stars_service.create_order = Mock(return_value={
            "id": 15,
            "invoice_payload": "cosmonet-stars:15"
        })

        with (
            patch.object(
                menu,
                "is_registered_user",
                return_value=True
            ),
            patch.object(
                menu,
                "SubscriptionService",
                return_value=subscription_service
            ),
            patch.object(
                menu,
                "StarsPaymentService",
                return_value=stars_service
            )
        ):
            await menu.select_stars_payment(callback)

        stars_service.create_order.assert_called_once()
        invoice = callback.message.answer_invoice.await_args.kwargs
        self.assertEqual(invoice["currency"], "XTR")
        self.assertEqual(invoice["prices"][0].amount, 119)
        self.assertEqual(
            invoice["payload"],
            "cosmonet-stars:15"
        )

    async def test_card_method_creates_robokassa_link(self):
        callback = Mock()
        callback.data = "pay_card:lite"
        callback.from_user = SimpleNamespace(id=1001)
        callback.answer = AsyncMock()
        callback.message = Mock()
        callback.message.edit_reply_markup = AsyncMock()
        callback.message.answer = AsyncMock()

        subscription_service = Mock()
        subscription_service.get_purchase_action = AsyncMock(
            return_value={"success": True, "action": "create", "client": None}
        )
        payment_service = Mock()
        payment_service.is_configured = True
        payment_service.create_order = Mock(return_value={"id": 15})
        payment_service.payment_url = Mock(
            return_value="https://auth.robokassa.ru/Merchant/Index.aspx?InvId=15"
        )

        with (
            patch.object(menu, "is_registered_user", return_value=True),
            patch.object(menu, "SubscriptionService", return_value=subscription_service),
            patch.object(menu, "RobokassaPaymentService", return_value=payment_service),
        ):
            await menu.select_card_payment(callback)

        payment_service.create_order.assert_called_once()
        text = callback.message.answer.await_args.args[0]
        markup = callback.message.answer.await_args.kwargs["reply_markup"]
        self.assertIn("Robokassa", text)
        self.assertEqual(
            markup.inline_keyboard[0][0].url,
            "https://auth.robokassa.ru/Merchant/Index.aspx?InvId=15",
        )
    async def test_pre_checkout_query_is_answered(self):
        query = Mock()
        query.from_user = SimpleNamespace(id=1001)
        query.invoice_payload = "cosmonet-stars:1"
        query.currency = "XTR"
        query.total_amount = 79
        query.answer = AsyncMock()
        service = Mock()
        service.validate_checkout = Mock(
            return_value=(True, None)
        )

        with patch.object(
            menu,
            "StarsPaymentService",
            return_value=service
        ):
            await menu.process_stars_pre_checkout(query)

        query.answer.assert_awaited_once_with(
            ok=True,
            error_message=None
        )

    async def test_successful_payment_is_passed_to_service(self):
        payment = SimpleNamespace(
            currency="XTR",
            total_amount=79,
            invoice_payload="cosmonet-stars:1",
            telegram_payment_charge_id="tg-charge-3",
            provider_payment_charge_id=""
        )
        message = Mock()
        message.from_user = SimpleNamespace(id=1001)
        message.successful_payment = payment
        service = Mock()
        service.process_payment = AsyncMock(return_value={
            "success": True,
            "status": "paid",
            "error": None,
            "order": {
                "id": 1,
                "payment_amount": 79,
                "devices": 1
            },
            "client": {
                "sub_id": "sub-1",
                "expiry_time": 1_900_000_000_000
            }
        })

        with (
            patch.object(
                menu,
                "StarsPaymentService",
                return_value=service
            ),
            patch.object(
                menu,
                "send_stars_payment_result",
                new_callable=AsyncMock
            ) as send_result
        ):
            await menu.process_successful_stars_payment(message)

        service.process_payment.assert_awaited_once()
        send_result.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
