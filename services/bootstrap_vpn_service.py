from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import aiohttp

import database
from config import (
    BOOTSTRAP_REALITY_PUBLIC_KEY,
    BOOTSTRAP_REALITY_SHORT_ID,
    BOOTSTRAP_VPN_ENABLED,
    BOOTSTRAP_VPN_HOST,
    BOOTSTRAP_VPN_SNI,
    BOOTSTRAP_XUI_API_TOKEN,
    BOOTSTRAP_XUI_BASE_URL,
    BOOTSTRAP_XUI_INBOUND_ID,
)


class BootstrapVpnService:
    """Manages disposable clients in the isolated Bootstrap 3X-UI panel."""

    def is_configured(self) -> bool:
        return all((
            BOOTSTRAP_VPN_ENABLED,
            BOOTSTRAP_XUI_BASE_URL,
            BOOTSTRAP_XUI_API_TOKEN,
            BOOTSTRAP_XUI_INBOUND_ID is not None,
            BOOTSTRAP_VPN_HOST,
            BOOTSTRAP_VPN_SNI,
            BOOTSTRAP_REALITY_PUBLIC_KEY,
        ))

    async def create_profile(
        self,
        *,
        session_id: str,
        expires_at: datetime,
    ) -> dict[str, str] | None:
        if not self.is_configured():
            return None

        await self.cleanup_expired()
        client_id = str(uuid.uuid4())
        expiry_time = int(expires_at.timestamp() * 1000)
        result = await self._request_json(
            "POST",
            "/panel/api/clients/add",
            payload={
                "client": {
                    "id": client_id,
                    "email": f"bootstrap-{session_id}",
                    "limitIp": 1,
                    "flow": "xtls-rprx-vision",
                    "totalGB": 64 * 1024 * 1024,
                    "expiryTime": expiry_time,
                    "enable": True,
                    "comment": "CosmoNet Telegram authorization",
                    "reset": 0,
                },
                "inboundIds": [BOOTSTRAP_XUI_INBOUND_ID],
            },
        )
        if not result["success"]:
            raise RuntimeError(result["error"] or "Bootstrap 3X-UI is unavailable.")

        if not await self._reload_inbound():
            await self._delete_client(f"bootstrap-{session_id}")
            raise RuntimeError("Bootstrap Xray configuration could not be reloaded.")

        self._save_client(session_id, client_id, expiry_time)
        return {
            "vlessUri": self._build_vless_uri(client_id),
            "expiresAt": expires_at.astimezone(timezone.utc).isoformat(),
        }

    async def revoke_for_session(self, session_id: str) -> None:
        client = self._get_client(session_id)
        if not client:
            return
        await self._delete_client(f"bootstrap-{session_id}")
        self._delete_client_record(session_id)

    async def cleanup_expired(self) -> None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        for client in self._get_expired_clients(now_ms):
            await self._delete_client(f"bootstrap-{client['session_id']}")
            self._delete_client_record(client["session_id"])

    def _build_vless_uri(self, client_id: str) -> str:
        query = {
            "encryption": "none",
            "security": "reality",
            "sni": BOOTSTRAP_VPN_SNI,
            "fp": "chrome",
            "pbk": BOOTSTRAP_REALITY_PUBLIC_KEY,
            "type": "tcp",
            "flow": "xtls-rprx-vision",
        }
        if BOOTSTRAP_REALITY_SHORT_ID:
            query["sid"] = BOOTSTRAP_REALITY_SHORT_ID
        encoded_query = "&".join(
            f"{quote(key)}={quote(value)}" for key, value in query.items()
        )
        return (
            f"vless://{client_id}@{BOOTSTRAP_VPN_HOST}:10443?{encoded_query}"
            "#CosmoNet%20Telegram%20authorization"
        )

    async def _delete_client(self, email: str) -> None:
        if not self.is_configured():
            return
        result = await self._request_json(
            "POST",
            f"/panel/api/clients/del/{quote(email, safe='')}",
        )
        if result["success"]:
            await self._reload_inbound()

    async def _reload_inbound(self) -> bool:
        inbound = await self._request_json(
            "GET",
            f"/panel/api/inbounds/get/{BOOTSTRAP_XUI_INBOUND_ID}",
        )
        config = inbound.get("obj")
        if not inbound["success"] or not isinstance(config, dict):
            return False
        result = await self._request_json(
            "POST",
            f"/panel/api/inbounds/update/{BOOTSTRAP_XUI_INBOUND_ID}",
            payload=config,
        )
        return result["success"]

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{BOOTSTRAP_XUI_BASE_URL.rstrip('/')}{path}"
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {BOOTSTRAP_XUI_API_TOKEN}",
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=timeout,
            ) as session:
                async with session.request(method, url, json=payload) as response:
                    raw = await response.text()
        except aiohttp.ClientError as error:
            return {"success": False, "error": str(error)}

        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        if response.status >= 400 or not data.get("success"):
            return {
                "success": False,
                "error": data.get("msg") or f"3X-UI returned HTTP {response.status}",
            }
        return {"success": True, "error": None, "obj": data.get("obj")}

    @staticmethod
    def _init_db() -> None:
        with database.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_bootstrap_vpn_clients (
                    session_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    expires_at_ms INTEGER NOT NULL
                )
            """)
            conn.commit()

    def _save_client(self, session_id: str, client_id: str, expires_at_ms: int) -> None:
        self._init_db()
        with database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_bootstrap_vpn_clients "
                "(session_id, client_id, expires_at_ms) VALUES (?, ?, ?)",
                (session_id, client_id, expires_at_ms),
            )
            conn.commit()

    def _get_client(self, session_id: str) -> dict[str, Any] | None:
        self._init_db()
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT session_id, client_id, expires_at_ms "
                "FROM app_bootstrap_vpn_clients WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def _get_expired_clients(self, now_ms: int) -> list[dict[str, Any]]:
        self._init_db()
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT session_id, client_id, expires_at_ms "
                "FROM app_bootstrap_vpn_clients WHERE expires_at_ms <= ?",
                (now_ms,),
            ).fetchall()
            return [dict(row) for row in rows]

    def _delete_client_record(self, session_id: str) -> None:
        self._init_db()
        with database.get_connection() as conn:
            conn.execute(
                "DELETE FROM app_bootstrap_vpn_clients WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
