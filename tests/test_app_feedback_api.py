import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ["ADMIN_IDS"] = "100,200"

from services.bootstrap_vpn_service import BootstrapVpnService
from services.app_feedback_api import (
    FeedbackPayload,
    create_app,
    deliver_feedback,
    format_feedback_message,
    parse_feedback_payload,
)
from services.windows_app_release import WindowsAppRelease


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


class FakeWebhookYooKassaService:
    async def process_notification(self, payload):
        return {"status": "ignored"}


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

    async def test_payment_creation_is_rate_limited_per_account(self):
        payment_service = FakeYooKassaService()
        client = TestClient(TestServer(create_app(
            FakeBot(),
            auth_service=FakeAuthService(),
            yookassa_service=payment_service,
        )))
        await client.start_server()

        try:
            for _ in range(3):
                response = await client.post(
                    "/api/app/payments/yookassa",
                    headers={"Authorization": "Bearer token"},
                    json={"tariffCode": "lite"},
                )
                self.assertEqual(response.status, 200)
            response = await client.post(
                "/api/app/payments/yookassa",
                headers={"Authorization": "Bearer token"},
                json={"tariffCode": "lite"},
            )
            self.assertEqual(response.status, 429)
            self.assertEqual(payment_service.create_order.call_count, 3)
        finally:
            await client.close()

    async def test_yookassa_webhook_is_rate_limited(self):
        payment_service = FakeWebhookYooKassaService()
        client = TestClient(TestServer(create_app(FakeBot(), yookassa_service=payment_service)))
        await client.start_server()

        try:
            for _ in range(30):
                response = await client.post("/payments/yookassa/result", json={"event": "ignored"})
                self.assertEqual(response.status, 200)
            response = await client.post("/payments/yookassa/result", json={"event": "ignored"})
            self.assertEqual(response.status, 429)
        finally:
            await client.close()

    async def test_yookassa_return_shows_payment_status_page(self):
        client = TestClient(TestServer(create_app(FakeBot())))
        await client.start_server()

        try:
            response = await client.get("/payments/yookassa/return")

            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "text/html")
            self.assertIn("Спасибо за оплату", await response.text())
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

    async def test_windows_release_endpoint_uses_current_release_and_update_deep_link(self):
        release = WindowsAppRelease(
            version="0.2.19",
            download_url="https://api.example.invalid:18443/downloads/CosmoNet-Setup-0.2.19.rar",
        )
        with patch("services.app_feedback_api.get_windows_app_release", AsyncMock(return_value=release)):
            client = TestClient(TestServer(create_app(FakeBot(), bot_username="CosmoNetBot")))
            await client.start_server()
            try:
                response = await client.get("/api/app/windows-release")
                payload = await response.json()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(payload, {
                    "version": "0.2.19",
                    "telegramDeepLink": "tg://resolve?domain=CosmoNetBot&start=desktop_update",
                    "telegramWebLink": "https://web.telegram.org/k/#?tgaddr=tg%3A%2F%2Fresolve%3Fdomain%3DCosmoNetBot%26start%3Ddesktop_update",
                })
            finally:
                await client.close()


class FakeStartAuthService:
    def create_login_session(self, *, device_id, device_name, platform):
        return {
            "sessionId": "bootstrap-session",
            "expiresAt": "2030-01-01T00:00:00+00:00",
        }


class FakeBootstrapVpnService:
    async def create_profile(self, *, session_id, expires_at):
        return [
            {
                "vlessUri": "vless://ws-profile",
                "expiresAt": expires_at.isoformat(),
                "transport": "ws",
            },
            {
                "vlessUri": "vless://tcp-profile",
                "expiresAt": expires_at.isoformat(),
                "transport": "tcp",
            },
        ]

    async def revoke_for_session(self, session_id):
        return None


class BootstrapAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_start_returns_disposable_bootstrap_profile(self):
        client = TestClient(TestServer(create_app(
            FakeBot(),
            auth_service=FakeStartAuthService(),
            bootstrap_vpn_service=FakeBootstrapVpnService(),
            bot_username="CosmoNetBot",
        )))
        await client.start_server()

        try:
            response = await client.post(
                "/api/app/auth/start",
                json={"deviceId": "device-1", "deviceName": "PC", "platform": "windows"},
            )
            payload = await response.json()

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["telegramDeepLink"], "tg://resolve?domain=CosmoNetBot&start=auth_bootstrap-session")
            self.assertEqual(payload["bootstrapVpn"]["vlessUri"], "vless://ws-profile")
            self.assertEqual(
                [profile["transport"] for profile in payload["bootstrapVpns"]],
                ["ws", "tcp"],
            )
        finally:
            await client.close()

    def test_bootstrap_profiles_prioritize_ws_and_use_tcp_tls_fallback(self):
        with patch.multiple(
            "services.bootstrap_vpn_service",
            BOOTSTRAP_WS_VPN_HOST="vpn.example.invalid",
            BOOTSTRAP_WS_TLS_SERVER_NAME="api.example.invalid",
            BOOTSTRAP_WS_PATH="/cosmonet-auth",
            BOOTSTRAP_WS_PORT=10444,
            BOOTSTRAP_TCP_VPN_HOST="vpn.example.invalid",
            BOOTSTRAP_TCP_TLS_SERVER_NAME="api.example.invalid",
            BOOTSTRAP_TCP_PORT=10445,
        ):
            service = BootstrapVpnService()
            ws_uri = service._build_ws_vless_uri("client-id")
            tcp_uri = service._build_tcp_vless_uri("client-id")

        self.assertIn("vless://client-id@vpn.example.invalid:10444", ws_uri)
        self.assertIn("security=tls", ws_uri)
        self.assertIn("type=ws", ws_uri)
        self.assertIn("vless://client-id@vpn.example.invalid:10445", tcp_uri)
        self.assertIn("security=tls", tcp_uri)
        self.assertIn("type=tcp", tcp_uri)


if __name__ == "__main__":
    unittest.main()
