import os
import unittest
from unittest.mock import AsyncMock, Mock

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


class FakeAuthService:
    def get_token_owner(self, token):
        return {"telegram_id": 1001, "device_id": "device-1"} if token == "token" else None


class FakeYooKassaService:
    is_configured = True

    def __init__(self):
        self.subscription_service = Mock()
        self.subscription_service.get_purchase_action = AsyncMock(
            return_value={"success": True, "action": "create", "client": None}
        )
        self.create_order = Mock(return_value={"id": 17})
        self.create_payment = AsyncMock(return_value="https://yookassa.ru/checkout/17")


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

    async def test_authenticated_app_can_create_yookassa_payment(self):
        payment_service = FakeYooKassaService()
        client = TestClient(TestServer(create_app(
            FakeBot(),
            auth_service=FakeAuthService(),
            yookassa_service=payment_service,
        )))
        await client.start_server()

        try:
            response = await client.post(
                "/api/app/payments/yookassa",
                headers={"Authorization": "Bearer token"},
                json={"tariffCode": "lite"},
            )

            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), {
                "orderId": 17,
                "paymentUrl": "https://yookassa.ru/checkout/17",
            })
            payment_service.create_order.assert_called_once()
            self.assertEqual(payment_service.create_order.call_args.kwargs["telegram_id"], 1001)
            self.assertEqual(payment_service.create_order.call_args.kwargs["tariff"].code, "lite")
        finally:
            await client.close()

    async def test_payment_endpoint_requires_authorization(self):
        client = TestClient(TestServer(create_app(
            FakeBot(),
            auth_service=FakeAuthService(),
            yookassa_service=FakeYooKassaService(),
        )))
        await client.start_server()

        try:
            response = await client.post("/api/app/payments/yookassa", json={"tariffCode": "lite"})
            self.assertEqual(response.status, 401)
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()