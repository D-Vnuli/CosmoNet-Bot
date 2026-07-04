import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import database
from services.subscription_service import calculate_target_expiry_ms
from services.tariff_service import TARIFFS
from services.test_payment_service import TestPaymentService


class OrderTests(unittest.IsolatedAsyncioTestCase):
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

    def test_target_expiry_extends_from_later_date(self):
        day_ms = 24 * 60 * 60 * 1000
        now_ms = 1_700_000_000_000

        new_expiry = calculate_target_expiry_ms(
            None,
            30,
            now_ms=now_ms
        )
        renewal_expiry = calculate_target_expiry_ms(
            now_ms + 10 * day_ms,
            30,
            now_ms=now_ms
        )

        self.assertEqual(new_expiry, now_ms + 30 * day_ms)
        self.assertEqual(renewal_expiry, now_ms + 40 * day_ms)

    async def test_confirm_order_provisions_once_and_marks_paid(self):
        subscription_service = Mock()
        subscription_service.provision_subscription = AsyncMock(
            return_value={
                "success": True,
                "error": None,
                "client": {
                    "email": "1001",
                    "sub_id": "sub-1",
                    "enable": True
                }
            }
        )
        subscription_service.get_user_vpn_client = AsyncMock(
            return_value={
                "success": True,
                "error": None,
                "client": {"email": "1001", "sub_id": "sub-1"}
            }
        )
        service = TestPaymentService(subscription_service)
        order = service.create_order(
            telegram_id=1001,
            tariff=TARIFFS[0],
            purchase_result={
                "action": "create",
                "client": None
            }
        )

        first_result = await service.confirm_order(order["id"])
        second_result = await service.confirm_order(order["id"])

        self.assertTrue(first_result["success"])
        self.assertEqual(first_result["order"]["status"], "paid")
        self.assertEqual(second_result["status"], "already_paid")
        subscription_service.provision_subscription.assert_awaited_once_with(
            telegram_id=1001,
            devices=1,
            target_expiry_ms=order["target_expiry_ms"]
        )

    async def test_failed_order_can_be_retried_with_same_target_expiry(self):
        subscription_service = Mock()
        subscription_service.provision_subscription = AsyncMock(side_effect=[
            {
                "success": False,
                "error": "temporary",
                "client": None
            },
            {
                "success": True,
                "error": None,
                "client": {"email": "1001"}
            }
        ])
        service = TestPaymentService(subscription_service)
        order = service.create_order(
            telegram_id=1001,
            tariff=TARIFFS[1],
            purchase_result={
                "action": "renew",
                "client": {"expiry_time": 1_800_000_000_000}
            }
        )

        first_result = await service.confirm_order(order["id"])
        second_result = await service.confirm_order(order["id"])

        self.assertFalse(first_result["success"])
        self.assertEqual(first_result["order"]["status"], "failed")
        self.assertTrue(second_result["success"])
        calls = (
            subscription_service
            .provision_subscription
            .await_args_list
        )
        self.assertEqual(
            calls[0].kwargs["target_expiry_ms"],
            calls[1].kwargs["target_expiry_ms"]
        )


if __name__ == "__main__":
    unittest.main()
