import os
import json
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from services.xui_service import XUIService


class ProvisioningXUIService(XUIService):
    def __init__(self, inbounds):
        super().__init__()
        self.inbound_id = None
        self.provisioning_inbound_ids = []
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

        if path.startswith("/panel/api/inbounds/update/"):
            inbound_id = int(path.rsplit("/", 1)[-1])

            for inbound in self.inbounds:
                if inbound.get("id") == inbound_id:
                    inbound["settings"] = payload["settings"]

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

    async def test_create_syncs_reality_primary_and_ws_fallback(self):
        service = ProvisioningXUIService([
            {
                "id": 6,
                "remark": "CosmoNet REALITY",
                "enable": True,
                "protocol": "vless",
                "streamSettings": {"network": "tcp", "security": "reality"},
                "settings": {"clients": []}
            },
            {
                "id": 3,
                "remark": "CosmoNet WS",
                "enable": True,
                "protocol": "vless",
                "streamSettings": {"network": "ws", "security": "none"},
                "settings": {"clients": []}
            }
        ])
        service.provisioning_inbound_ids = [6, 3]

        result = await service.create_client(
            email="1001",
            telegram_id=1001,
            devices=3,
            expiry_time_ms=1_800_000_000_000
        )

        self.assertTrue(result["success"], result.get("error"))
        self.assertEqual(len(service.requests), 2)

        reality_settings = json.loads(service.requests[0][2]["settings"])
        ws_settings = json.loads(service.requests[1][2]["settings"])
        reality_client = reality_settings["clients"][0]
        ws_client = ws_settings["clients"][0]

        self.assertEqual(reality_client["email"], "1001")
        self.assertEqual(ws_client["email"], "1001")
        self.assertEqual(reality_client["id"], ws_client["id"])
        self.assertEqual(reality_client["subId"], ws_client["subId"])
        self.assertEqual(reality_client["flow"], "xtls-rprx-vision")
        self.assertEqual(ws_client["flow"], "")
        self.assertEqual(reality_client["limitIp"], 3)
        self.assertEqual(ws_client["limitIp"], 3)


if __name__ == "__main__":
    unittest.main()
