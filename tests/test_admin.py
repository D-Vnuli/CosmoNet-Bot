import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from handlers import admin


class FakeMessage:
    def __init__(self, user_id=42):
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class AdminHandlersTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_stats_uses_xui_client_statuses(self):
        message = FakeMessage()
        xui = Mock()
        xui.get_all_clients = AsyncMock(return_value={
            "success": True,
            "error": None,
            "clients": [
                {"email": "1001", "enable": True},
                {"email": "1002", "enable": False},
                {"email": "manual-client", "enable": True}
            ]
        })

        with (
            patch.object(admin, "ADMIN_IDS", [42]),
            patch.object(
                admin,
                "get_all_telegram_ids",
                return_value=[1001, 1002, 1003]
            ),
            patch.object(admin, "XUIService", return_value=xui)
        ):
            await admin.admin_stats(message)

        text = message.answers[0][0]
        self.assertIn("VPN-профилей в 3X-UI:</b> 3", text)
        self.assertIn("Активных VPN-профилей:</b> 2", text)
        self.assertIn("Отключённых VPN-профилей:</b> 1", text)
        self.assertIn("Связано с пользователями бота:</b> 2", text)
        xui.get_all_clients.assert_awaited_once_with()

    async def test_admin_users_distinguishes_client_states(self):
        message = FakeMessage()
        xui = Mock()
        xui.get_clients_by_emails = AsyncMock(return_value={
            "success": True,
            "error": None,
            "clients": {
                "1001": {"enable": True, "expiry_time": 0},
                "1002": {"enable": False, "expiry_time": 0}
            }
        })
        users = [
            (1001, "active", "Active", "2026-01-01 10:00:00"),
            (1002, "disabled", "Disabled", "2026-01-02 10:00:00"),
            (1003, "new", "New", "2026-01-03 10:00:00")
        ]

        with (
            patch.object(admin, "ADMIN_IDS", [42]),
            patch.object(admin, "get_all_users", return_value=users),
            patch.object(admin, "XUIService", return_value=xui)
        ):
            await admin.admin_users(message)

        text = message.answers[0][0]
        self.assertIn("🟢 активна", text)
        self.assertIn("🟠 отключена", text)
        self.assertIn("🔴 VPN-профиль не создан", text)


if __name__ == "__main__":
    unittest.main()
