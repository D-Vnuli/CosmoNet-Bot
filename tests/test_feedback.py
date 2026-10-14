import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from handlers import menu
from handlers.app_auth import AuthDeepLinkFilter, is_auth_deep_link
from services.windows_app_release import WindowsAppRelease


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
        self.answer_photo = AsyncMock()
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

        self.assertIn("📡 Статус", subscription_buttons)
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

    async def test_apps_message_lists_mobile_clients_and_current_cosmonet_for_windows(self):
        message = FakeMessage()

        release = WindowsAppRelease(
            version="0.2.8",
            download_url="https://api.example.invalid:18443/downloads/CosmoNet-Setup-0.2.8.rar",
        )
        with patch.object(menu, "get_windows_app_release", AsyncMock(return_value=release)):
            await menu.apps(message)

        text = message.answer.await_args.args[0]
        self.assertIn("v2RayTun", text)
        self.assertIn("Happ", text)
        self.assertIn("CosmoNet v0.2.8 для Windows", text)
        self.assertIn(release.download_url, text)
        self.assertNotIn("демо-тестировании", text)

    async def test_desktop_update_uses_the_same_current_release_as_apps(self):
        message = FakeMessage()
        release = WindowsAppRelease(
            version="0.2.19",
            download_url="https://api.example.invalid:18443/downloads/CosmoNet-Setup-0.2.19.rar",
        )
        with patch.object(menu, "get_windows_app_release", AsyncMock(return_value=release)):
            await menu.apps(message)
            apps_text = message.answer.await_args.args[0]
            await menu.send_windows_release_update(message)

        update_text = message.answer.await_args.args[0]
        update_keyboard = message.answer.await_args.kwargs["reply_markup"]
        self.assertIn(release.version, apps_text)
        self.assertIn(release.version, update_text)
        self.assertEqual(update_keyboard.inline_keyboard[0][0].url, release.download_url)

    def test_start_payload_routing_keeps_auth_and_update_separate(self):
        self.assertTrue(is_auth_deep_link("/start auth_session"))
        self.assertFalse(is_auth_deep_link("/start desktop_update"))
        self.assertFalse(is_auth_deep_link("/start"))
        self.assertTrue(menu.is_desktop_update_deep_link("/start desktop_update"))
        self.assertFalse(menu.is_desktop_update_deep_link("/start auth_session"))
        self.assertFalse(menu.is_desktop_update_deep_link("/start unknown_payload"))

    async def test_start_filters_route_auth_and_desktop_update_without_swallowing_normal_start(self):
        auth_filter = AuthDeepLinkFilter()
        update_filter = menu.DesktopUpdateDeepLinkFilter()

        self.assertTrue(await auth_filter(SimpleNamespace(text="/start auth_session")))
        self.assertFalse(await update_filter(SimpleNamespace(text="/start auth_session")))
        self.assertFalse(await auth_filter(SimpleNamespace(text="/start desktop_update")))
        self.assertTrue(await update_filter(SimpleNamespace(text="/start desktop_update")))
        self.assertFalse(await auth_filter(SimpleNamespace(text="/start")))
        self.assertFalse(await update_filter(SimpleNamespace(text="/start")))

    async def test_normal_start_remains_the_welcome_flow(self):
        message = FakeMessage()
        message.from_user.first_name = "Cosmo"
        message.from_user.last_name = "User"
        message.from_user.language_code = "ru"
        state = FakeState()
        with patch.object(menu, "WELCOME_BANNER", menu.Path("missing-banner.png")):
            await menu.start_handler(message, state)

        self.assertTrue(state.cleared)
        self.assertIn("CosmoNet", message.answer.await_args.args[0])

if __name__ == "__main__":
    unittest.main()
