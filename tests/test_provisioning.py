import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from services.xui_service import XUIService


class ProvisioningXUIService(XUIService):
    def __init__(self, inbounds):
        super().__init__()
        self.inbound_id = None
        self.inbounds = inbounds
        self.requests = []

    async def get_inbounds(self):
        return {
            "success": True,
            "error": None,
            "inbounds": self.inbounds
        }

    async def _request_json(self, method, path, *, payload=None):
        self.requests.append((method, path, payload))
        return {
            "success": True,
            "error": None,
            "obj": None
        }

    async def _verify_client_state(
        self,
        *,
        email,
        devices,
        expiry_time_ms
    ):
        return {
            "success": True,
            "error": None,
            "client": {
                "email": email,
                "limit_ip": devices,
                "expiry_time": expiry_time_ms,
                "enable": True,
                "sub_id": "sub-1"
            }
        }


class XUIProvisioningTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_uses_vless_inbound_with_existing_clients(self):
        service = ProvisioningXUIService([
            {
                "id": 1,
                "enable": True,
                "protocol": "vless",
                "settings": {"clients": []}
            },
            {
                "id": 3,
                "enable": True,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"email": "one"},
                        {"email": "two"}
                    ]
                }
            }
        ])

        result = await service.create_client(
            email="1001",
            telegram_id=1001,
            devices=3,
            expiry_time_ms=1_800_000_000_000
        )

        self.assertTrue(result["success"])
        method, path, payload = service.requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/panel/api/clients/add")
        self.assertEqual(payload["inboundIds"], [3])
        self.assertEqual(payload["client"]["email"], "1001")
        self.assertEqual(payload["client"]["limitIp"], 3)
        self.assertEqual(
            payload["client"]["expiryTime"],
            1_800_000_000_000
        )

    async def test_update_preserves_identity_and_sets_exact_limits(self):
        service = ProvisioningXUIService([])
        client = {
            "email": "1001",
            "id": "uuid-1",
            "sub_id": "sub-1",
            "enable": False,
            "expiry_time": 1_700_000_000_000,
            "total_gb": 0,
            "limit_ip": 1,
            "flow": "",
            "password": "",
            "auth": "",
            "security": "",
            "tg_id": 1001,
            "comment": "",
            "reset": 0,
            "created_at": 1_600_000_000_000
        }

        result = await service.update_client(
            client=client,
            devices=5,
            expiry_time_ms=1_900_000_000_000
        )

        self.assertTrue(result["success"])
        method, path, payload = service.requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/panel/api/clients/update/1001")
        self.assertEqual(payload["id"], "uuid-1")
        self.assertEqual(payload["subId"], "sub-1")
        self.assertEqual(payload["limitIp"], 5)
        self.assertEqual(payload["expiryTime"], 1_900_000_000_000)
        self.assertTrue(payload["enable"])


if __name__ == "__main__":
    unittest.main()
