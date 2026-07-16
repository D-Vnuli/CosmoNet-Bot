import unittest

from aiohttp.test_utils import TestClient, TestServer

from services.xui_metadata_api import (
    SubscriptionMetadata,
    _clients_from_inbound,
    _metadata_from_client,
    create_app,
)


class FakeMetadataClient:
    async def get_subscription_metadata(self, sub_id, client_id):
        if sub_id != "sub-17" and client_id != "client-17":
            return None
        return SubscriptionMetadata(3, True, None)


class XuiMetadataApiTests(unittest.IsolatedAsyncioTestCase):
    def test_reads_metadata_from_xui_inbound_settings(self):
        clients = _clients_from_inbound({
            "settings": '{"clients":[{"subId":"sub-17","id":"client-17","limitIp":3,"enable":true,"expiryTime":0}]}'
        })
        metadata = _metadata_from_client(clients[0])
        self.assertEqual(metadata.device_limit, 3)
        self.assertTrue(metadata.is_enabled)
        self.assertIsNone(metadata.expires_at_unix_milliseconds)

    def test_converts_expiry_seconds_to_milliseconds(self):
        metadata = _metadata_from_client({"limitIp": 0, "enable": True, "expiryTime": 1_800_000_000})
        self.assertEqual(metadata.expires_at_unix_milliseconds, 1_800_000_000_000)

    async def test_returns_metadata_by_subscription_id(self):
        client = TestClient(TestServer(create_app(FakeMetadataClient())))
        await client.start_server()
        try:
            response = await client.get("/api/app/subscription/device-limit?subId=sub-17")
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), {"deviceLimit": 3, "isEnabled": True, "expiresAtUnixMilliseconds": None})
        finally:
            await client.close()

    async def test_returns_metadata_by_client_id(self):
        client = TestClient(TestServer(create_app(FakeMetadataClient())))
        await client.start_server()
        try:
            response = await client.get("/api/app/subscription/device-limit?clientId=client-17")
            self.assertEqual(response.status, 200)
            self.assertTrue((await response.json())["isEnabled"])
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()