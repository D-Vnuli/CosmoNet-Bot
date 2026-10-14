import os
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage

from services.broadcast_service import BroadcastAudience, BroadcastService


def telegram_method():
    return SendMessage(chat_id=1, text="test")


class BroadcastServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_recipients_supports_all_segments(self):
        service = BroadcastService()
        xui = Mock()
        xui.get_clients_by_emails = AsyncMock(return_value={
            "success": True,
            "error": None,
            "clients": {
                "1001": {"enable": True},
                "1002": {"enable": False}
            }
        })

        with (
            patch(
                "services.broadcast_service.get_all_telegram_ids",
                return_value=[1001, 1002, 1003, 1001]
            ),
            patch(
                "services.broadcast_service.XUIService",
                return_value=xui
            )
        ):
            all_users = await service.resolve_recipients(
                BroadcastAudience.ALL
            )
            active_users = await service.resolve_recipients(
                BroadcastAudience.ACTIVE
            )
            inactive_users = await service.resolve_recipients(
                BroadcastAudience.INACTIVE
            )

        self.assertEqual(all_users, [1001, 1002, 1003])
        self.assertEqual(active_users, [1001])
        self.assertEqual(inactive_users, [1002, 1003])

    async def test_start_prevents_parallel_broadcasts_and_sends_report(self):
        service = BroadcastService()
        service.SEND_INTERVAL_SECONDS = 0
        bot = Mock()
        bot.copy_message = AsyncMock(return_value=Mock())
        bot.send_message = AsyncMock(return_value=Mock())
        arguments = {
            "bot": bot,
            "admin_id": 42,
            "source_chat_id": 42,
            "source_message_id": 77,
            "recipient_ids": [1001, 1002]
        }

        self.assertTrue(service.start(**arguments))
        self.assertFalse(service.start(**arguments))

        await service.wait_until_finished()

        self.assertEqual(bot.copy_message.await_count, 2)
        bot.copy_message.assert_has_awaits([
            call(
                chat_id=1001,
                from_chat_id=42,
                message_id=77,
                protect_content=True
            ),
            call(
                chat_id=1002,
                from_chat_id=42,
                message_id=77,
                protect_content=True
            )
        ])
        report = bot.send_message.await_args.kwargs["text"]
        self.assertIn("Доставлено:</b> 2", report)
        self.assertIn("Прочие ошибки:</b> 0", report)

    async def test_delivery_retries_temporary_errors(self):
        service = BroadcastService()
        bot = Mock()
        bot.copy_message = AsyncMock(side_effect=[
            TelegramRetryAfter(
                method=telegram_method(),
                message="retry",
                retry_after=1
            ),
            TelegramNetworkError(
                method=telegram_method(),
                message="network"
            ),
            Mock()
        ])

        with patch(
            "services.broadcast_service.asyncio.sleep",
            new=AsyncMock()
        ) as sleep:
            status = await service._deliver_message(
                bot=bot,
                telegram_id=1001,
                source_chat_id=42,
                source_message_id=77
            )

        self.assertEqual(status, "delivered")
        self.assertEqual(bot.copy_message.await_count, 3)
        self.assertEqual(sleep.await_count, 2)

    async def test_delivery_classifies_blocked_user_as_unavailable(self):
        service = BroadcastService()
        bot = Mock()
        bot.copy_message = AsyncMock(side_effect=TelegramForbiddenError(
            method=telegram_method(),
            message="bot was blocked"
        ))

        status = await service._deliver_message(
            bot=bot,
            telegram_id=1001,
            source_chat_id=42,
            source_message_id=77
        )

        self.assertEqual(status, "unavailable")

    async def test_report_contains_partial_delivery_statistics(self):
        service = BroadcastService()
        service.SEND_INTERVAL_SECONDS = 0
        service._deliver_message = AsyncMock(side_effect=[
            "delivered",
            "unavailable",
            "failed"
        ])
        bot = Mock()
        bot.send_message = AsyncMock(return_value=Mock())

        await service._run(
            bot=bot,
            admin_id=42,
            source_chat_id=42,
            source_message_id=77,
            recipient_ids=[1001, 1002, 1003]
        )

        report = bot.send_message.await_args.kwargs["text"]
        self.assertIn("Выбрано адресатов:</b> 3", report)
        self.assertIn("Доставлено:</b> 1", report)
        self.assertIn("чат недоступен:</b> 1", report)
        self.assertIn("Прочие ошибки:</b> 1", report)


if __name__ == "__main__":
    unittest.main()
