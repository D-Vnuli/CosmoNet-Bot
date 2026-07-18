import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import database
from services.robokassa_payment_service import (
    RobokassaPaymentService,
    RobokassaSettings,
)
from services.tariff_service import TARIFFS


class RobokassaPaymentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patcher = patch.object(
            database,
            "DB_PATH",
            Path(self.temp_dir.name) / "test.db",
        )
        self.db_path_patcher.start()
        database.init_db()
        self.settings = RobokassaSettings(
            merchant_login="cosmonet-test",
            password_1="password-one",
            password_2="password-two",
            is_test=True,
        )

    def tearDown(self):
        self.db_path_patcher.stop()
        self.temp_dir.cleanup()

    def create_service_and_order(self):
        subscription_service = Mock()
        service = RobokassaPaymentService(
            subscription_service=subscription_service,
            settings=self.settings,
        )
        order = service.create_order(
            telegram_id=1001,
            tariff=TARIFFS[0],
            purchase_result={"action": "create", "client": None},
        )
        return service, subscription_service, order

    def result_data(self, order, *, signature=""):
        amount = f"{order['payment_amount']:.6f}"
        expected = hashlib.md5(
            f"{amount}:{order['id']}:password-two".encode("utf-8")
        ).hexdigest()
        return {
            "OutSum": amount,
            "InvId": str(order["id"]),
            "SignatureValue": signature or expected,
        }

    def test_payment_url_contains_signed_order_and_test_flag(self):
        service, _, order = self.create_service_and_order()

        parameters = parse_qs(urlparse(service.payment_url(order)).query)

        self.assertEqual(parameters["MerchantLogin"], ["cosmonet-test"])
        self.assertEqual(parameters["OutSum"], ["50.00"])
        self.assertEqual(parameters["InvId"], [str(order["id"])])
        self.assertEqual(parameters["IsTest"], ["1"])
        expected = hashlib.md5(
            f"cosmonet-test:50.00:{order['id']}:password-one".encode("utf-8")
        ).hexdigest()
        self.assertEqual(parameters["SignatureValue"], [expected])

    async def test_valid_result_provisions_once_and_is_idempotent(self):
        service, subscription_service, order = self.create_service_and_order()
        subscription_service.provision_subscription = AsyncMock(
            return_value={
                "success": True,
                "error": None,
                "client": {"sub_id": "sub-1"},
            }
        )

        first = await service.process_result(self.result_data(order))
        second = await service.process_result(self.result_data(order))

        self.assertTrue(first["success"])
        self.assertEqual(first["status"], "paid")
        self.assertEqual(second["status"], "already_paid")
        subscription_service.provision_subscription.assert_awaited_once()

    async def test_invalid_signature_does_not_provision(self):
        service, subscription_service, order = self.create_service_and_order()
        subscription_service.provision_subscription = AsyncMock()

        result = await service.process_result(
            self.result_data(order, signature="not-a-signature")
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid")
        subscription_service.provision_subscription.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()