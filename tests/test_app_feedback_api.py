import os
import unittest

from aiohttp.test_utils import TestClient, TestServer

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ["ADMIN_IDS"] = "100,200"

from services.app_feedback_api import (
    FeedbackPayload,
    create_app,
    deliver_feedback,
    format_feedback_message,
    parse_feedback_payload,
)


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, *, chat_id, text):
        self.messages.append((chat_id, text))


class FeedbackApiTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_rejects_incomplete_payload(self):
        with self.assertRaises(ValueError):
            parse_feedback_payload({"name": "Анна", "contacts": "", "message": "Нужна помощь"})

    def test_message_escapes_html(self):
        text = format_feedback_message(
            FeedbackPayload("Анна <test>", "@anna", "Проверьте <подключение>")
        )

        self.assertIn("Анна &lt;test&gt;", text)
        self.assertIn("&lt;подключение&gt;", text)

    async def test_deliver_sends_message_to_each_admin(self):
        bot = FakeBot()
        payload = FeedbackPayload("Анна", "@anna", "Нужна помощь")

        delivered = await deliver_feedback(bot, [100, 200], payload)

        self.assertEqual(delivered, 2)
        self.assertEqual([chat_id for chat_id, _ in bot.messages], [100, 200])

    async def test_endpoint_delivers_valid_request(self):
        bot = FakeBot()
        client = TestClient(TestServer(create_app(bot)))
        await client.start_server()

        try:
            response = await client.post(
                "/api/app/feedback",
                json={
                    "name": "Анна",
                    "contacts": "@anna",
                    "message": "Нужна помощь с подключением",
                },
            )

            self.assertEqual(response.status, 200)
            self.assertTrue((await response.json())["delivered"])
            self.assertEqual([chat_id for chat_id, _ in bot.messages], [100, 200])
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()