import os
import unittest
from unittest.mock import AsyncMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from services.yookassa_payment_service import YooKassaPaymentService


class YooKassaPaymentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.order = {
            "id": 21,
            "telegram_id": 1001,
            "tariff_code": "lite",
            "devices": 1,
            "target_expiry_ms": 1_900_000_000_000,
            "payment_amount": 129,
        }
        self.payment = {
            "id": "payment-21",
            "metadata": {"order_id": "21"},
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "129.00", "currency": "RUB"},
        }

    async def test_confirmed_payment_provisions_and_completes_order(self):
        subscription_service = Mock()
        subscription_service.provision_subscription = AsyncMock(return_value={
            "success": True,
            "error": None,
            "client": {"expiry_time": self.order["target_expiry_ms"]},
        })
        service = YooKassaPaymentService(subscription_service)

        with (
            patch.object(service, "_request", AsyncMock(return_value=self.payment)),
            patch("services.yookassa_payment_service.get_order", return_value=self.order),
            patch("services.yookassa_payment_service.claim_yookassa_payment", return_value=("claimed", self.order)),
            patch("services.yookassa_payment_service.complete_order") as complete_order,
        ):
            result = await service.process_notification({
                "event": "payment.succeeded",
                "object": {"id": "payment-21"},
            })

        self.assertEqual(result["status"], "paid")
        subscription_service.provision_subscription.assert_awaited_once_with(
            telegram_id=1001,
            devices=1,
            target_expiry_ms=1_900_000_000_000,
        )
        complete_order.assert_called_once_with(21)

    async def test_invalid_amount_never_provisions_subscription(self):
        subscription_service = Mock()
        subscription_service.provision_subscription = AsyncMock()
        service = YooKassaPaymentService(subscription_service)
        invalid_payment = {**self.payment, "amount": {"value": "99.00", "currency": "RUB"}}

        with (
            patch.object(service, "_request", AsyncMock(return_value=invalid_payment)),
            patch("services.yookassa_payment_service.get_order", return_value=self.order),
            patch("services.yookassa_payment_service.claim_yookassa_payment") as claim_payment,
        ):
            result = await service.process_notification({
                "event": "payment.succeeded",
                "object": {"id": "payment-21"},
            })

        self.assertEqual(result["status"], "invalid")
        claim_payment.assert_not_called()
        subscription_service.provision_subscription.assert_not_awaited()

    async def test_duplicate_notification_does_not_extend_twice(self):
        service = YooKassaPaymentService(Mock())

        with (
            patch.object(service, "_request", AsyncMock(return_value=self.payment)),
            patch("services.yookassa_payment_service.get_order", return_value=self.order),
            patch("services.yookassa_payment_service.claim_yookassa_payment", return_value=("already_paid", self.order)),
        ):
            result = await service.process_notification({
                "event": "payment.succeeded",
                "object": {"id": "payment-21"},
            })

        self.assertEqual(result["status"], "already_paid")

    async def test_payment_creation_uses_configured_return_page(self):
        service = YooKassaPaymentService()
        response = {
            "id": "payment-21",
            "confirmation": {"confirmation_url": "https://yookassa.ru/checkout/21"},
        }

        with (
            patch("services.yookassa_payment_service.YOOKASSA_SHOP_ID", "shop"),
            patch("services.yookassa_payment_service.YOOKASSA_SECRET_KEY", "secret"),
            patch("services.yookassa_payment_service.YOOKASSA_RETURN_URL", "https://example.test/return"),
            patch.object(service, "_request", AsyncMock(return_value=response)) as request,
        ):
            payment_url = await service.create_payment(self.order)

        self.assertEqual(payment_url, "https://yookassa.ru/checkout/21")
        self.assertEqual(
            request.await_args.args[2]["confirmation"]["return_url"],
            "https://example.test/return",
        )

    async def test_failed_provision_can_be_retried_without_second_payment(self):
        subscription_service = Mock()
        subscription_service.provision_subscription = AsyncMock(return_value={
            "success": True,
            "error": None,
            "client": {"expiry_time": self.order["target_expiry_ms"]},
        })
        service = YooKassaPaymentService(subscription_service)

        with (
            patch("services.yookassa_payment_service.claim_failed_yookassa_order", return_value=self.order),
            patch("services.yookassa_payment_service.complete_order") as complete_order,
            patch("services.yookassa_payment_service.get_order", return_value=self.order),
        ):
            result = await service.retry_provisioning(order_id=21, telegram_id=1001)

        self.assertEqual(result["status"], "paid")
        subscription_service.provision_subscription.assert_awaited_once()
        complete_order.assert_called_once_with(21)
