import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import database
from services.subscription_reminder_service import SubscriptionReminderService


class StubXUIService:
    def __init__(self, clients):
        self.clients = clients

    async def get_all_clients(self):
        return {
            "success": True,
            "error": None,
            "clients": self.clients,
        }


class SubscriptionReminderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cosmonet.db"
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        database.init_db()
        self.now_ms = 1_800_000_000_000

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    async def test_sends_three_and_one_day_reminders_once(self):
        day_ms = SubscriptionReminderService.DAY_MS
        service = SubscriptionReminderService(
            xui=StubXUIService([
                {
                    "email": "1001",
                    "enable": True,
                    "expiry_time": self.now_ms + 3 * day_ms,
                },
                {
                    "email": "1001",
                    "enable": True,
                    "expiry_time": self.now_ms + 3 * day_ms,
                },
                {
                    "email": "1002",
                    "enable": True,
                    "expiry_time": self.now_ms + day_ms,
                },
                {
                    "email": "manual-client",
                    "enable": True,
                    "expiry_time": self.now_ms + day_ms,
                },
            ]),
            now_ms=lambda: self.now_ms,
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await service.send_due_reminders(bot), 2)
        self.assertEqual(bot.send_message.await_count, 2)
        sent_texts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
        self.assertTrue(any("3 дня" in text for text in sent_texts))
        self.assertTrue(any("1 день" in text for text in sent_texts))

        self.assertEqual(await service.send_due_reminders(bot), 0)
        self.assertEqual(bot.send_message.await_count, 2)

    async def test_sends_expiration_once_and_ignores_inactive_clients(self):
        day_ms = SubscriptionReminderService.DAY_MS
        service = SubscriptionReminderService(
            xui=StubXUIService([
                {
                    "email": "1001",
                    "enable": False,
                    "expiry_time": self.now_ms + day_ms,
                },
                {
                    "email": "1002",
                    "enable": True,
                    "expiry_time": self.now_ms - day_ms,
                },
            ]),
            now_ms=lambda: self.now_ms,
        )
        bot = Mock()
        bot.send_message = AsyncMock()

        self.assertEqual(await service.send_due_reminders(bot), 1)
        text = bot.send_message.await_args.kwargs["text"]
        self.assertIn("Подписка CosmoNet закончилась", text)

        self.assertEqual(await service.send_due_reminders(bot), 0)
        self.assertEqual(bot.send_message.await_count, 1)


if __name__ == "__main__":
    unittest.main()
