import asyncio
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp

from config import (
    COSMONET_WINDOWS_FALLBACK_DOWNLOAD_URL,
    COSMONET_WINDOWS_FALLBACK_VERSION,
    COSMONET_WINDOWS_RELEASE_MANIFEST_URL,
)

_VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
_CACHE_TTL_SECONDS = 60
_REQUEST_TIMEOUT_SECONDS = 4
_EXPECTED_DOWNLOAD_HOST = "api.example.invalid"
_cache_lock = asyncio.Lock()


@dataclass(frozen=True)
class WindowsAppRelease:
    version: str
    download_url: str


def _is_valid_download_url(value: object) -> bool:
    if not isinstance(value, str):
        return False

    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == _EXPECTED_DOWNLOAD_HOST
        and parsed.port == 18443
        and parsed.path.startswith("/downloads/CosmoNet-Setup-")
        and parsed.path.endswith(".rar")
    )


def _fallback_release() -> WindowsAppRelease:
    if not _VERSION_PATTERN.fullmatch(COSMONET_WINDOWS_FALLBACK_VERSION):
        raise RuntimeError("COSMONET_WINDOWS_FALLBACK_VERSION must use X.Y.Z format")
    if not _is_valid_download_url(COSMONET_WINDOWS_FALLBACK_DOWNLOAD_URL):
        raise RuntimeError("COSMONET_WINDOWS_FALLBACK_DOWNLOAD_URL must point to the CosmoNet HTTPS download")

    return WindowsAppRelease(
        version=COSMONET_WINDOWS_FALLBACK_VERSION,
        download_url=COSMONET_WINDOWS_FALLBACK_DOWNLOAD_URL,
    )


_cached_release = _fallback_release()
_cache_expires_at = 0.0


async def get_windows_app_release() -> WindowsAppRelease:
    global _cached_release, _cache_expires_at

    if time.monotonic() < _cache_expires_at:
        return _cached_release

    async with _cache_lock:
        if time.monotonic() < _cache_expires_at:
            return _cached_release

        try:
            timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    COSMONET_WINDOWS_RELEASE_MANIFEST_URL,
                    headers={"Accept": "application/json"},
                ) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)

            version = payload.get("version") if isinstance(payload, dict) else None
            download_url = payload.get("downloadUrl") if isinstance(payload, dict) else None
            if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
                raise ValueError("The release manifest contains an invalid version")
            if not _is_valid_download_url(download_url):
                raise ValueError("The release manifest contains an invalid download URL")

            _cached_release = WindowsAppRelease(version=version, download_url=download_url)
            _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            _cached_release = _fallback_release()
            _cache_expires_at = time.monotonic() + 60

        return _cached_release
