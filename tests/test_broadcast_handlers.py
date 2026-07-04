import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from handlers import admin


class FakeState:
    def __init__(self, data=None):
        self.state = None
        self.data = data or {}
        self.cleared = False

    async def set_state(self, state):
        self.state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return self.data

    async def clear(self):
        self.state = None
        self.data = {}
        self.cleared = True


class FakeMessage:
    def __init__(
        self,
        *,
        user_id=42,
        text=None,
        photo=None,
        media_group_id=None
    ):
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=user_id)
        self.message_id = 77
        self.text = text
        self.photo = photo
        self.media_group_id = media_group_id
        self.bot = Mock()
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class BroadcastHandlersTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_start_opens_audience_selection(self):
        message = FakeMessage(text="📣 Рассылка")
        state = FakeState()
        service = Mock()
        service.is_running = False

        with (
            patch.object(admin, "ADMIN_IDS", [42]),
            patch.object(admin, "broadcast_service", service)
        ):
            await admin.broadcast_start(message, state)

        self.assertEqual(
            state.state,
            admin.BroadcastStates.choosing_audience
        )
        self.assertIn("Выберите группу", message.answers[0][0])

    async def test_content_starts_broadcast_without_confirmation(self):
        message = FakeMessage(text="Технические работы")
        state = FakeState(data={
            "audience": admin.BroadcastAudience.ALL.value
        })
        service = Mock()
        service.is_running = False
        service.resolve_recipients = AsyncMock(return_value=[1001, 1002])
        service.start = Mock(return_value=True)

        with (
            patch.object(admin, "ADMIN_IDS", [42]),
            patch.object(admin, "broadcast_service", service)
        ):
            await admin.broadcast_receive_content(message, state)

        self.assertTrue(state.cleared)
        service.start.assert_called_once_with(
            bot=message.bot,
            admin_id=42,
            source_chat_id=42,
            source_message_id=77,
            recipient_ids=[1001, 1002]
        )
        self.assertIn("Рассылка запущена", message.answers[0][0])

    async def test_unsupported_content_is_rejected(self):
        message = FakeMessage()
        state = FakeState(data={
            "audience": admin.BroadcastAudience.ALL.value
        })

        with patch.object(admin, "ADMIN_IDS", [42]):
            await admin.broadcast_receive_content(message, state)

        self.assertFalse(state.cleared)
        self.assertIn("Поддерживается только текст", message.answers[0][0])

    async def test_single_photo_starts_broadcast(self):
        message = FakeMessage(photo=[Mock()])
        state = FakeState(data={
            "audience": admin.BroadcastAudience.ALL.value
        })
        service = Mock()
        service.is_running = False
        service.resolve_recipients = AsyncMock(return_value=[1001])
        service.start = Mock(return_value=True)

        with (
            patch.object(admin, "ADMIN_IDS", [42]),
            patch.object(admin, "broadcast_service", service)
        ):
            await admin.broadcast_receive_content(message, state)

        self.assertTrue(state.cleared)
        service.start.assert_called_once()

    async def test_album_is_rejected_once(self):
        message = FakeMessage(
            photo=[Mock()],
            media_group_id="album-1"
        )
        state = FakeState(data={
            "audience": admin.BroadcastAudience.ALL.value
        })

        with patch.object(admin, "ADMIN_IDS", [42]):
            await admin.broadcast_reject_album(message, state)
            await admin.broadcast_reject_album(message, state)

        self.assertFalse(state.cleared)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("Альбомы не поддерживаются", message.answers[0][0])

    async def test_cancel_clears_state(self):
        message = FakeMessage(text="❌ Отмена")
        state = FakeState(data={
            "audience": admin.BroadcastAudience.ALL.value
        })

        with patch.object(admin, "ADMIN_IDS", [42]):
            await admin.broadcast_cancel(message, state)

        self.assertTrue(state.cleared)
        self.assertIn("Рассылка отменена", message.answers[0][0])

    async def test_non_admin_cannot_start_broadcast(self):
        message = FakeMessage(user_id=99, text="📣 Рассылка")
        state = FakeState()

        with patch.object(admin, "ADMIN_IDS", [42]):
            await admin.broadcast_start(message, state)

        self.assertIsNone(state.state)
        self.assertEqual(message.answers, [])


if __name__ == "__main__":
    unittest.main()
