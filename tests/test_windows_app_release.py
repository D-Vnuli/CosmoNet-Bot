import os
import unittest
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "123456:test-token")

from services import windows_app_release
from services.windows_app_release import _is_valid_download_url


class FakeManifestResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self):
        if self._error:
            raise self._error

    async def json(self, content_type=None):
        return self._payload


class FakeManifestSession:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def get(self, *args, **kwargs):
        return self._response


class WindowsAppReleaseTests(unittest.IsolatedAsyncioTestCase):
    def test_accepts_only_the_expected_https_download_url(self):
        self.assertTrue(
            _is_valid_download_url(
                "https://api.example.invalid:18443/downloads/CosmoNet-Setup-0.2.8.rar"
            )
        )

    def test_rejects_an_untrusted_manifest_url(self):
        self.assertFalse(
            _is_valid_download_url("https://example.com/downloads/CosmoNet-Setup-0.2.8.rar")
        )

    async def test_valid_manifest_returns_current_release(self):
        response = FakeManifestResponse({
            "version": "0.2.19",
            "downloadUrl": "https://api.example.invalid:18443/downloads/CosmoNet-Setup-0.2.19.rar",
        })
        with patch.object(windows_app_release.aiohttp, "ClientSession", return_value=FakeManifestSession(response)), \
             patch.object(windows_app_release, "_cache_expires_at", 0.0):
            release = await windows_app_release.get_windows_app_release()

        self.assertEqual(release.version, "0.2.19")
        self.assertEqual(release.download_url, response._payload["downloadUrl"])

    async def test_unavailable_manifest_uses_existing_fallback_release(self):
        response = FakeManifestResponse(error=windows_app_release.aiohttp.ClientError())
        with patch.object(windows_app_release.aiohttp, "ClientSession", return_value=FakeManifestSession(response)), \
             patch.object(windows_app_release, "_cache_expires_at", 0.0):
            release = await windows_app_release.get_windows_app_release()

        self.assertEqual(release, windows_app_release._fallback_release())


if __name__ == "__main__":
    unittest.main()
