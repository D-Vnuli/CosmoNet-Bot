import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from services.xui_service import XUIService


class StubXUIService(XUIService):
    def __init__(self, result):
        self.result = result

    async def get_inbounds(self):
        return self.result


class XUIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_clients_by_emails_returns_only_requested_clients(self):
        service = StubXUIService({
            "success": True,
            "error": None,
            "inbounds": [
                {
                    "id": 7,
                    "remark": "main",
                    "port": 443,
                    "protocol": "vless",
                    "settings": (
                        '{"clients": ['
                        '{"email": "1001", "id": "uuid-1", "subId": "sub-1", '
                        '"enable": true, "expiryTime": 1700000000000, "limitIp": 2},'
                        '{"email": "9999", "id": "uuid-2", "enable": true}'
                        ']}'
                    ),
                    "clientStats": [
                        {
                            "email": "1001",
                            "up": 100,
                            "down": 200,
                            "total": 300
                        }
                    ]
                }
            ]
        })

        result = await service.get_clients_by_emails([1001, 1002])

        self.assertTrue(result["success"])
        self.assertEqual(set(result["clients"]), {"1001"})
        self.assertEqual(result["clients"]["1001"]["sub_id"], "sub-1")
        self.assertEqual(result["clients"]["1001"]["up"], 100)
        self.assertEqual(result["clients"]["1001"]["down"], 200)

    async def test_get_all_clients_returns_every_panel_profile(self):
        service = StubXUIService({
            "success": True,
            "error": None,
            "inbounds": [
                {
                    "id": 7,
                    "settings": {
                        "clients": [
                            {"email": "1001", "enable": True},
                            {"email": "manual-client", "enable": False}
                        ]
                    },
                    "clientStats": []
                }
            ]
        })

        result = await service.get_all_clients()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["clients"]), 2)
        self.assertEqual(
            {client["email"] for client in result["clients"]},
            {"1001", "manual-client"}
        )

    async def test_get_clients_by_emails_propagates_panel_error(self):
        service = StubXUIService({
            "success": False,
            "error": "panel unavailable",
            "inbounds": []
        })

        result = await service.get_clients_by_emails([1001])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "panel unavailable")
        self.assertEqual(result["clients"], {})

    async def test_get_client_by_email_uses_batch_lookup(self):
        service = StubXUIService({
            "success": True,
            "error": None,
            "inbounds": [
                {
                    "id": 7,
                    "settings": {
                        "clients": [
                            {"email": "1001", "enable": False}
                        ]
                    },
                    "clientStats": []
                }
            ]
        })

        result = await service.get_client_by_email("1001")

        self.assertTrue(result["success"])
        self.assertEqual(result["client"]["email"], "1001")
        self.assertFalse(result["client"]["enable"])

    async def test_get_clients_by_emails_ignores_malformed_panel_data(self):
        service = StubXUIService({
            "success": True,
            "error": None,
            "inbounds": [
                None,
                {
                    "settings": {"clients": None},
                    "clientStats": None
                }
            ]
        })

        result = await service.get_clients_by_emails([1001])

        self.assertTrue(result["success"])
        self.assertEqual(result["clients"], {})


if __name__ == "__main__":
    unittest.main()
