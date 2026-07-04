import json
from collections.abc import Iterable
from datetime import datetime

import aiohttp

from config import XUI_BASE_URL, XUI_API_TOKEN


class XUIService:
    def __init__(self):
        self.base_url = XUI_BASE_URL.rstrip("/") if XUI_BASE_URL else None
        self.api_token = XUI_API_TOKEN

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_token)

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}"
        }

    async def get_inbounds(self):
        if not self.is_configured():
            return {
                "success": False,
                "error": "3X-UI не настроен в .env",
                "inbounds": []
            }

        url = f"{self.base_url}/panel/api/inbounds/list"

        try:
            async with aiohttp.ClientSession(headers=self.get_headers()) as session:
                async with session.get(url) as response:
                    data = await response.json(content_type=None)

                    if not data.get("success"):
                        return {
                            "success": False,
                            "error": data.get("msg", "Ошибка получения inbound"),
                            "inbounds": []
                        }

                    return {
                        "success": True,
                        "error": None,
                        "inbounds": data.get("obj", [])
                    }

        except Exception as error:
            return {
                "success": False,
                "error": f"Ошибка подключения к 3X-UI: {error}",
                "inbounds": []
            }

    async def get_client_by_email(self, email: str):
        result = await self.get_clients_by_emails([email])

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "client": None
            }

        return {
            "success": True,
            "error": None,
            "client": result["clients"].get(str(email))
        }

    async def get_clients_by_emails(self, emails: Iterable[str | int]):
        requested_emails = {str(email) for email in emails}

        if not requested_emails:
            return {
                "success": True,
                "error": None,
                "clients": {}
            }

        result = await self.get_all_clients()

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "clients": {}
            }

        found_clients = {}

        for client in result["clients"]:
            email = str(client.get("email"))

            if email in requested_emails and email not in found_clients:
                found_clients[email] = client

        return {
            "success": True,
            "error": None,
            "clients": found_clients
        }

    async def get_all_clients(self):
        result = await self.get_inbounds()

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "clients": []
            }

        found_clients = []

        for inbound in result["inbounds"] or []:
            if not isinstance(inbound, dict):
                continue

            settings_raw = inbound.get("settings", {})

            if isinstance(settings_raw, str):
                try:
                    settings = json.loads(settings_raw)
                except json.JSONDecodeError:
                    settings = {}
            elif isinstance(settings_raw, dict):
                settings = settings_raw
            else:
                settings = {}

            clients = settings.get("clients", [])
            client_stats = inbound.get("clientStats", [])

            if not isinstance(clients, list):
                clients = []

            if not isinstance(client_stats, list):
                client_stats = []

            stats_by_email = {
                str(item.get("email")): item
                for item in client_stats
                if isinstance(item, dict)
            }

            for client in clients:
                if not isinstance(client, dict):
                    continue

                email = str(client.get("email"))
                stats = stats_by_email.get(email)
                found_clients.append({
                    "email": client.get("email"),
                    "id": client.get("id"),
                    "sub_id": client.get("subId"),
                    "enable": client.get("enable", False),
                    "expiry_time": client.get("expiryTime"),
                    "total_gb": client.get("totalGB", 0),
                    "inbound_id": inbound.get("id"),
                    "inbound_remark": inbound.get("remark"),
                    "inbound_port": inbound.get("port"),
                    "protocol": inbound.get("protocol"),
                    "limit_ip": client.get("limitIp", 0),
                    "up": stats.get("up", 0) if stats else 0,
                    "down": stats.get("down", 0) if stats else 0,
                    "total": stats.get("total", 0) if stats else 0,
                })

        return {
            "success": True,
            "error": None,
            "clients": found_clients
        }


def format_bytes(size: int) -> str:
    if not size:
        return "0 Б"

    power = 1024
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]

    index = 0
    while size >= power and index < len(units) - 1:
        size /= power
        index += 1

    return f"{size:.2f} {units[index]}"


def format_expiry_time(expiry_time: int | None) -> str:
    if not expiry_time or expiry_time == 0:
        return "Без ограничения"

    try:
        expiry_time_seconds = expiry_time / 1000
        return datetime.fromtimestamp(expiry_time_seconds).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "Неизвестно"
