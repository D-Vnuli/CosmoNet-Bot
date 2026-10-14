import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from aiogram.exceptions import TelegramAPIError

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import database
from services.stars_payment_service import StarsPaymentService
from services.tariff_service import PAID_TARIFFS
from services.subscription_reminder_service import SubscriptionReminderService
from services.subscription_service import (
    SubscriptionService,
    TRIAL_DURATION_MS,
    TRIAL_TRAFFIC_BYTES,
)


class TrialXUI:
    def __init__(self, client=None, traffic=0):
        self.client = client
        self.traffic = traffic
        self.traffic_records = None
        self.create_client = AsyncMock(side_effect=self._create_client)
        self.update_client = AsyncMock(side_effect=self._update_client)

    async def get_client_by_email(self, email):
        return {"success": True, "error": None, "client": self.client}

    async def _create_client(self, **kwargs):
        self.client = {
            "email": kwargs["email"],
            "id": "stable-uuid",
            "sub_id": "stable-sub-id",
            "limit_ip": kwargs["devices"],
            "expiry_time": kwargs["expiry_time_ms"],
            "total_gb": kwargs["total_gb"],
            "enable": True,
        }
        return {"success": True, "error": None, "client": self.client}

    async def _update_client(self, **kwargs):
        client = dict(kwargs["client"])
        client.update({
            "limit_ip": kwargs["devices"],
            "expiry_time": kwargs["expiry_time_ms"],
            "total_gb": kwargs.get("total_gb", client.get("total_gb", 0)),
            "enable": kwargs.get("enabled", True),
        })
        self.client = client
        return {"success": True, "error": None, "client": client}

    def _records_for_email(self, email):
        if self.traffic_records is not None:
            return [
                {**record, "email": str(email)}
                for record in self.traffic_records
            ]
        if not self.client:
            return []
        return [{
            **self.client,
            "email": str(email),
            "up": self.traffic,
            "down": 0,
            "inbound_id": 1,
        }]

    async def get_client_records_by_emails(self, emails):
        return {
            "success": True,
            "error": None,
            "clients": {
                str(email): self._records_for_email(email)
                for email in emails
                if self.client
            },
        }

    async def get_all_clients(self):
        return {
            "success": True,
            "error": None,
            "clients": self._records_for_email(self.client["email"])
            if self.client else [],
        }


class TrialTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cosmonet.db"
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        database.init_db()
        database.add_user_if_not_exists(1001, None, "Test")

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    async def test_trial_is_atomic_and_preserves_client_identity(self):
        xui = TrialXUI()
        service = SubscriptionService(xui=xui)

        result = await service.activate_trial(1001)

        self.assertTrue(result["success"])
        self.assertEqual(result["ends_at_ms"] - database.get_trial_state(1001)["trial_started_at"], TRIAL_DURATION_MS)
        self.assertEqual(result["client"]["total_gb"], TRIAL_TRAFFIC_BYTES)
        self.assertEqual(result["client"]["id"], "stable-uuid")
        self.assertEqual(result["client"]["sub_id"], "stable-sub-id")
        self.assertEqual((await service.activate_trial(1001))["status"], "used")
        self.assertEqual(xui.create_client.await_count, 1)

    async def test_failed_panel_activation_releases_trial(self):
        xui = TrialXUI()
        xui.create_client = AsyncMock(return_value={
            "success": False, "error": "panel unavailable", "client": None,
        })

        result = await SubscriptionService(xui=xui).activate_trial(1001)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "provisioning_failed")
        self.assertEqual(database.get_trial_state(1001)["trial_used"], 0)

    async def test_paid_upgrade_clears_trial_limit_without_identity_change(self):
        xui = TrialXUI()
        service = SubscriptionService(xui=xui)
        trial = await service.activate_trial(1001)

        paid = await service.provision_subscription(
            telegram_id=1001,
            devices=3,
            target_expiry_ms=trial["ends_at_ms"] + TRIAL_DURATION_MS,
        )

        self.assertTrue(paid["success"])
        self.assertEqual(paid["client"]["id"], trial["client"]["id"])
        self.assertEqual(paid["client"]["sub_id"], trial["client"]["sub_id"])
        self.assertEqual(paid["client"]["total_gb"], 0)
        self.assertTrue(paid["client"]["enable"])
        self.assertEqual(database.get_trial_state(1001)["trial_end_reason"], "paid")

    async def test_paid_order_during_trial_starts_from_payment_time(self):
        xui = TrialXUI()
        service = SubscriptionService(xui=xui)
        await service.activate_trial(1001)
        now_ms = 1_800_000_000_000

        with patch(
            "services.stars_payment_service.calculate_target_expiry_ms",
            side_effect=lambda current, days: now_ms + days,
        ) as target_expiry:
            StarsPaymentService(service).create_order(
                telegram_id=1001,
                tariff=PAID_TARIFFS[0],
                purchase_result={"action": "renew", "client": xui.client},
            )

        self.assertIsNone(target_expiry.call_args.args[0])

    async def test_trial_checker_disables_on_traffic_and_notifies_once(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        xui.traffic = TRIAL_TRAFFIC_BYTES
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"] - 1,
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await checker.check_due_trials(bot), 1)
        self.assertEqual(xui.update_client.await_args.kwargs["enabled"], False)
        self.assertEqual(database.get_trial_state(1001)["trial_end_reason"], "traffic")
        self.assertEqual(await checker.check_due_trials(bot), 0)
        self.assertEqual(bot.send_message.await_count, 1)

    async def test_trial_traffic_is_aggregated_across_inbounds(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        xui.traffic_records = [
            {**xui.client, "inbound_id": 6, "up": 300 * 1024 * 1024, "down": 0},
            {**xui.client, "inbound_id": 3, "up": 250 * 1024 * 1024, "down": 0},
        ]
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"] - 1,
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await checker.check_due_trials(bot), 1)
        self.assertEqual(database.get_trial_state(1001)["trial_end_reason"], "traffic")

    async def test_trial_traffic_below_aggregate_limit_stays_active(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        xui.traffic_records = [
            {**xui.client, "inbound_id": 6, "up": 300 * 1024 * 1024, "down": 0},
            {**xui.client, "inbound_id": 3, "up": 150 * 1024 * 1024, "down": 0},
        ]
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"] - 1,
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await checker.check_due_trials(bot), 0)
        self.assertIsNone(database.get_trial_state(1001)["trial_end_reason"])
        xui.update_client.assert_not_awaited()

    async def test_trial_traffic_does_not_double_count_mirrored_inbounds(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        xui.traffic_records = [
            {
                **xui.client,
                "inbound_id": 1,
                "up": 852_358,
                "down": 273_903_434,
            },
            {
                **xui.client,
                "inbound_id": 3,
                "up": 852_358,
                "down": 273_903_434,
            },
        ]
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"] - 1,
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await checker.check_due_trials(bot), 0)
        self.assertIsNone(database.get_trial_state(1001)["trial_end_reason"])
        xui.update_client.assert_not_awaited()

    async def test_expired_trial_skips_normal_expiry_notification(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"],
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await checker.send_due_reminders(bot), 0)
        self.assertEqual(await checker.check_due_trials(bot), 1)
        self.assertEqual(bot.send_message.await_count, 1)
        self.assertIn("Пробный период CosmoNet закончился", bot.send_message.await_args.kwargs["text"])

    async def test_trial_notification_retries_only_on_next_checker_cycle(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"],
        )
        bot = Mock()
        bot.send_message = AsyncMock(side_effect=[
            TelegramAPIError(None, "temporary"),
            None,
        ])

        self.assertEqual(await checker.check_due_trials(bot), 0)
        self.assertEqual(bot.send_message.await_count, 1)
        self.assertEqual(database.get_trial_state(1001)["trial_exhausted_notified"], 0)

        self.assertEqual(await checker.check_due_trials(bot), 1)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertEqual(database.get_trial_state(1001)["trial_exhausted_notified"], 1)

    async def test_trial_checker_disables_on_time_limit(self):
        xui = TrialXUI()
        trial = await SubscriptionService(xui=xui).activate_trial(1001)
        checker = SubscriptionReminderService(
            xui=xui,
            now_ms=lambda: trial["ends_at_ms"],
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await checker.check_due_trials(bot), 1)
        self.assertEqual(database.get_trial_state(1001)["trial_end_reason"], "time")
        self.assertEqual(bot.send_message.await_count, 1)


if __name__ == "__main__":
    unittest.main()
