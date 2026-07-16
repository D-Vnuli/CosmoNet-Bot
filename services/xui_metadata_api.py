from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic
from typing import Any

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

MAX_REQUESTS_PER_WINDOW = 12
RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class SubscriptionMetadata:
    device_limit: int
    is_enabled: bool
    expires_at_unix_milliseconds: int | None


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, client_key: str) -> bool:
        now = monotonic()
        requests = self._requests[client_key]
        while requests and now - requests[0] >= RATE_LIMIT_WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= MAX_REQUESTS_PER_WINDOW:
            return False
        requests.append(now)
        return True


class XuiMetadataClient:
    def __init__(self, base_url: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token

    async def get_subscription_metadata(
        self,
        sub_id: str | None,
        client_id: str | None,
    ) -> SubscriptionMetadata | None:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"Authorization": f"Bearer {self._api_token}", "Accept": "application/json"}
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(f"{self._base_url}/panel/api/inbounds/list") as response:
                response.raise_for_status()
                data = await response.json(content_type=None)

        for inbound in data.get("obj") or data.get("inbounds") or []:
            for client in _clients_from_inbound(inbound):
                matches_sub_id = sub_id and str(client.get("subId", "")) == sub_id
                matches_client_id = client_id and str(client.get("id", "")) == client_id
                if matches_sub_id or matches_client_id:
                    return _metadata_from_client(client)
        return None


def create_app(metadata_client: XuiMetadataClient) -> web.Application:
    app = web.Application(client_max_size=8 * 1024)
    rate_limiter = RateLimiter()

    async def get_subscription_metadata(request: web.Request) -> web.Response:
        sub_id = request.query.get("subId", "").strip()
        client_id = request.query.get("clientId", "").strip()
        if (not sub_id and not client_id) or len(sub_id) > 128 or len(client_id) > 128:
            return web.json_response({"message": "Subscription not found."}, status=400)
        if not rate_limiter.allow(request.remote or "unknown"):
            return web.json_response({"message": "Too many requests."}, status=429)
        try:
            metadata = await metadata_client.get_subscription_metadata(sub_id or None, client_id or None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return web.json_response({"message": "3X-UI is unavailable."}, status=503)
        if metadata is None:
            return web.json_response({"message": "Subscription not found."}, status=404)
        return web.json_response({
            "deviceLimit": metadata.device_limit,
            "isEnabled": metadata.is_enabled,
            "expiresAtUnixMilliseconds": metadata.expires_at_unix_milliseconds,
        })

    app.router.add_get("/api/app/subscription/device-limit", get_subscription_metadata)
    return app


def _metadata_from_client(client: dict[str, Any]) -> SubscriptionMetadata:
    device_limit = _read_non_negative_int(client.get("limitIp"), default=0)
    expires_at = _read_non_negative_int(client.get("expiryTime"), default=0)
    if 0 < expires_at < 10_000_000_000:
        expires_at *= 1000
    return SubscriptionMetadata(
        device_limit=device_limit,
        is_enabled=client.get("enable") is not False,
        expires_at_unix_milliseconds=expires_at or None,
    )


def _read_non_negative_int(value: Any, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result >= 0 else default


def _clients_from_inbound(inbound: Any) -> list[dict[str, Any]]:
    if not isinstance(inbound, dict):
        return []
    settings = inbound.get("settings", {})
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError:
            return []
    clients = settings.get("clients", []) if isinstance(settings, dict) else []
    return [client for client in clients if isinstance(client, dict)]


def main() -> None:
    base_url = os.getenv("XUI_BASE_URL", "").strip()
    api_token = os.getenv("XUI_API_TOKEN", "").strip()
    host = os.getenv("XUI_METADATA_HOST", "127.0.0.1").strip()
    port = int(os.getenv("XUI_METADATA_PORT", "8090"))
    if not base_url or not api_token:
        raise RuntimeError("XUI_BASE_URL and XUI_API_TOKEN are required.")
    web.run_app(create_app(XuiMetadataClient(base_url, api_token)), host=host, port=port)


if __name__ == "__main__":
    main()