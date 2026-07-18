import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from handlers import menu


class FakeState:
    def __init__(self):
        self.state = None
        self.cleared = False

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.cleared = True
        self.state = None


class FakeMessage:
    def __init__(self):
        self.from_user = SimpleNamespace(
            id=1001,
            username="cosmo_user",
            full_name="Cosmo User"
        )
        self.bot = Mock()
        self.bot.send_message = AsyncMock()
        self.answer = AsyncMock()
        self.copy_to = AsyncMock()


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    def test_menu_order_and_feedback_button(self):
        subscription_buttons = [
            button.text
            for row in menu.subscription_menu.keyboard
            for button in row
        ]
        info_buttons = [
            button.text
            for row in menu.info_menu.keyboard
            for button in row
        ]

        self.assertIn("🛒 Тарифы", subscription_buttons)
        self.assertIn("🛰 Конфигурация", subscription_buttons)
        self.assertIn("🔐 Как подключиться", info_buttons)
        self.assertIn("📱 Приложения", info_buttons)
        self.assertIn("💬 Поддержка", info_buttons)
    async def test_feedback_start_waits_for_message(self):
        message = FakeMessage()
        state = FakeState()

        await menu.feedback_start(message, state)

        self.assertEqual(
            state.state,
            menu.FeedbackStates.waiting_message
        )
        text = message.answer.await_args.args[0]
        self.assertIn("скриншот", text)

    async def test_feedback_is_copied_with_user_identity(self):
        message = FakeMessage()
        state = FakeState()

        with patch.object(menu, "ADMIN_IDS", [42]):
            await menu.feedback_receive(message, state)

        header = message.bot.send_message.await_args.kwargs["text"]
        self.assertIn("@cosmo_user", header)
        self.assertIn("<code>1001</code>", header)
        self.assertIn("tg://user?id=1001", header)
        message.copy_to.assert_awaited_once_with(chat_id=42)
        self.assertTrue(state.cleared)
        confirmation = message.answer.await_args.args[0]
        self.assertIn("отправлено администратору", confirmation)

    async def test_apps_message_contains_only_cosmonet_windows_client(self):
        message = FakeMessage()

        await menu.apps(message)

        text = message.answer.await_args.args[0]
        self.assertIn("CosmoNet для Windows", text)
        self.assertNotIn("Hiddify", text)

if __name__ == "__main__":
    unittest.main()
