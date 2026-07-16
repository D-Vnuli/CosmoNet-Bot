import json
import secrets
import uuid
from collections.abc import Iterable
from datetime import datetime
from urllib.parse import quote

import aiohttp

from config import (
    XUI_API_TOKEN,
    XUI_BASE_URL,
    XUI_INBOUND_ID,
    XUI_PROVISIONING_INBOUND_IDS
)


class XUIService:
    def __init__(self):
        self.base_url = XUI_BASE_URL.rstrip("/") if XUI_BASE_URL else None
        self.api_token = XUI_API_TOKEN
        self.inbound_id = XUI_INBOUND_ID
        self.provisioning_inbound_ids = XUI_PROVISIONING_INBOUND_IDS

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_token)

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json"
        }

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None
    ):
        if not self.is_configured():
            return {
                "success": False,
                "error": "3X-UI не настроен в .env",
                "obj": None
            }

        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=30)

        try:
            async with aiohttp.ClientSession(
                headers=self.get_headers(),
                timeout=timeout
            ) as session:
                async with session.request(
                    method,
                    url,
                    json=payload
                ) as response:
                    raw_body = await response.text()

                    try:
                        data = json.loads(raw_body) if raw_body else {}
                    except json.JSONDecodeError:
                        data = {}

                    if response.status >= 400:
                        return {
                            "success": False,
                            "error": (
                                data.get("msg")
                                or f"3X-UI вернул HTTP {response.status}"
                            ),
                            "obj": None
                        }

                    if not data.get("success"):
                        return {
                            "success": False,
                            "error": data.get(
                                "msg",
                                "3X-UI не подтвердил операцию"
                            ),
                            "obj": data.get("obj")
                        }

                    return {
                        "success": True,
                        "error": None,
                        "obj": data.get("obj")
                    }

        except Exception as error:
            return {
                "success": False,
                "error": f"Ошибка подключения к 3X-UI: {error}",
                "obj": None
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
                    "flow": client.get("flow", ""),
                    "password": client.get("password", ""),
                    "auth": client.get("auth", ""),
                    "security": client.get("security", ""),
                    "tg_id": client.get("tgId", 0),
                    "comment": client.get("comment", ""),
                    "reset": client.get("reset", 0),
                    "created_at": client.get("created_at", 0),
                    "updated_at": client.get("updated_at", 0),
                    "up": stats.get("up", 0) if stats else 0,
                    "down": stats.get("down", 0) if stats else 0,
                    "total": stats.get("total", 0) if stats else 0,
                })

        return {
            "success": True,
            "error": None,
            "clients": found_clients
        }

    async def get_provisioning_inbound_id(self):
        result = await self.get_inbounds()

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "inbound_id": None
            }

        inbounds = [
            inbound
            for inbound in result["inbounds"] or []
            if isinstance(inbound, dict)
        ]

        if self.inbound_id is not None:
            selected = next(
                (
                    inbound
                    for inbound in inbounds
                    if inbound.get("id") == self.inbound_id
                ),
                None
            )

            if not selected:
                return {
                    "success": False,
                    "error": (
                        f"В 3X-UI не найден inbound "
                        f"с ID {self.inbound_id}"
                    ),
                    "inbound_id": None
                }

            if (
                not selected.get("enable", True)
                or selected.get("protocol") != "vless"
            ):
                return {
                    "success": False,
                    "error": (
                        f"Inbound {self.inbound_id} должен быть "
                        "активным и использовать VLESS"
                    ),
                    "inbound_id": None
                }

            return {
                "success": True,
                "error": None,
                "inbound_id": self.inbound_id
            }

        candidates = [
            inbound
            for inbound in inbounds
            if (
                inbound.get("enable", True)
                and inbound.get("protocol") == "vless"
            )
        ]

        if not candidates:
            return {
                "success": False,
                "error": "Не найден активный VLESS inbound в 3X-UI",
                "inbound_id": None
            }

        candidates.sort(
            key=self._get_inbound_clients_count,
            reverse=True
        )
        return {
            "success": True,
            "error": None,
            "inbound_id": candidates[0].get("id")
        }

    @staticmethod
    def _get_inbound_clients_count(inbound: dict) -> int:
        settings_raw = inbound.get("settings", {})

        if isinstance(settings_raw, str):
            try:
                settings = json.loads(settings_raw)
            except json.JSONDecodeError:
                return 0
        elif isinstance(settings_raw, dict):
            settings = settings_raw
        else:
            return 0

        clients = settings.get("clients", [])
        return len(clients) if isinstance(clients, list) else 0

    @staticmethod
    def _parse_json_field(value, fallback):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback

        if isinstance(value, dict):
            return value

        return fallback

    @staticmethod
    def _get_clients_from_inbound(inbound: dict) -> list[dict]:
        settings = XUIService._parse_json_field(
            inbound.get("settings", {}),
            {}
        )
        clients = settings.get("clients", [])
        return clients if isinstance(clients, list) else []

    @staticmethod
    def _get_stream_settings(inbound: dict) -> dict:
        return XUIService._parse_json_field(
            inbound.get("streamSettings", {}),
            {}
        )

    @staticmethod
    def _get_client_flow_for_inbound(inbound: dict) -> str:
        stream_settings = XUIService._get_stream_settings(inbound)

        if stream_settings.get("security") == "reality":
            return "xtls-rprx-vision"

        return ""

    @staticmethod
    def _build_sub_id() -> str:
        return secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]

    async def get_provisioning_inbound_ids(self):
        result = await self.get_inbounds()

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "inbound_ids": []
            }

        inbounds = [
            inbound
            for inbound in result["inbounds"] or []
            if isinstance(inbound, dict)
        ]

        configured_ids = (
            self.provisioning_inbound_ids
            or ([self.inbound_id] if self.inbound_id is not None else [])
        )

        if configured_ids:
            selected_inbounds = []

            for inbound_id in configured_ids:
                selected = next(
                    (
                        inbound
                        for inbound in inbounds
                        if inbound.get("id") == inbound_id
                    ),
                    None
                )

                if not selected:
                    return {
                        "success": False,
                        "error": (
                            f"Р’ 3X-UI РЅРµ РЅР°Р№РґРµРЅ inbound "
                            f"СЃ ID {inbound_id}"
                        ),
                        "inbound_ids": []
                    }

                if (
                    not selected.get("enable", True)
                    or selected.get("protocol") != "vless"
                ):
                    return {
                        "success": False,
                        "error": (
                            f"Inbound {inbound_id} РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ "
                            "Р°РєС‚РёРІРЅС‹Рј Рё РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ VLESS"
                        ),
                        "inbound_ids": []
                    }

                selected_inbounds.append(selected)

            return {
                "success": True,
                "error": None,
                "inbound_ids": [
                    inbound.get("id")
                    for inbound in selected_inbounds
                ]
            }

        single_result = await self.get_provisioning_inbound_id()

        if not single_result["success"]:
            return {
                "success": False,
                "error": single_result["error"],
                "inbound_ids": []
            }

        return {
            "success": True,
            "error": None,
            "inbound_ids": [single_result["inbound_id"]]
        }

    async def _update_inbound_settings(self, inbound: dict, settings: dict):
        payload = dict(inbound)
        payload.pop("clientStats", None)
        payload["settings"] = json.dumps(
            settings,
            ensure_ascii=False,
            separators=(",", ":")
        )

        return await self._request_json(
            "POST",
            f"/panel/api/inbounds/update/{inbound['id']}",
            payload=payload
        )

    async def _sync_client_across_inbounds(
        self,
        *,
        email: str,
        telegram_id: int,
        devices: int,
        expiry_time_ms: int,
        existing_client: dict | None = None
    ):
        inbound_ids_result = await self.get_provisioning_inbound_ids()

        if not inbound_ids_result["success"]:
            return {
                "success": False,
                "error": inbound_ids_result["error"],
                "client": None
            }

        inbounds_result = await self.get_inbounds()

        if not inbounds_result["success"]:
            return {
                "success": False,
                "error": inbounds_result["error"],
                "client": None
            }

        target_id_list = inbound_ids_result["inbound_ids"]
        target_ids = set(target_id_list)
        inbounds_by_id = {
            inbound.get("id"): inbound
            for inbound in inbounds_result["inbounds"] or []
            if isinstance(inbound, dict)
        }
        target_inbounds = [
            inbounds_by_id[inbound_id]
            for inbound_id in target_id_list
            if inbound_id in inbounds_by_id
        ]

        existing_clients = []

        for inbound in target_inbounds:
            for client in self._get_clients_from_inbound(inbound):
                if str(client.get("email")) == str(email):
                    existing_clients.append(client)

        source_client = (
            existing_client
            or (existing_clients[0] if existing_clients else None)
            or {}
        )
        client_id = source_client.get("id") or str(uuid.uuid4())
        sub_id = source_client.get("sub_id") or source_client.get("subId")

        if not sub_id:
            sub_id = self._build_sub_id()

        if not telegram_id:
            telegram_id = source_client.get("tg_id", 0) or source_client.get("tgId", 0)

        if not telegram_id and str(email).isdigit():
            telegram_id = int(email)

        for inbound in target_inbounds:
            settings = self._parse_json_field(inbound.get("settings", {}), {})
            clients = settings.setdefault("clients", [])

            if not isinstance(clients, list):
                clients = []
                settings["clients"] = clients

            current = next(
                (
                    client
                    for client in clients
                    if str(client.get("email")) == str(email)
                ),
                None
            )

            if current is None:
                current = {}
                clients.append(current)

            current.update({
                "id": client_id,
                "flow": self._get_client_flow_for_inbound(inbound),
                "email": email,
                "limitIp": devices,
                "totalGB": current.get(
                    "totalGB",
                    source_client.get("total_gb", 0)
                ),
                "expiryTime": expiry_time_ms,
                "enable": True,
                "tgId": telegram_id,
                "subId": sub_id,
                "comment": current.get(
                    "comment",
                    source_client.get("comment", "CosmoNet subscription")
                ),
                "reset": current.get(
                    "reset",
                    source_client.get("reset", 0)
                )
            })

            result = await self._update_inbound_settings(inbound, settings)

            if not result["success"]:
                return {
                    "success": False,
                    "error": result["error"],
                    "client": None
                }

        return await self._verify_client_state_across_inbounds(
            email=email,
            devices=devices,
            expiry_time_ms=expiry_time_ms,
            inbound_ids=target_id_list
        )

    async def create_client(
        self,
        *,
        email: str,
        telegram_id: int,
        devices: int,
        expiry_time_ms: int
    ):
        if self.provisioning_inbound_ids:
            return await self._sync_client_across_inbounds(
                email=email,
                telegram_id=telegram_id,
                devices=devices,
                expiry_time_ms=expiry_time_ms
            )

        inbound_result = await self.get_provisioning_inbound_id()

        if not inbound_result["success"]:
            return {
                "success": False,
                "error": inbound_result["error"],
                "client": None
            }

        payload = {
            "client": {
                "email": email,
                "limitIp": devices,
                "totalGB": 0,
                "expiryTime": expiry_time_ms,
                "enable": True,
                "tgId": telegram_id,
                "comment": "CosmoNet test order",
                "reset": 0
            },
            "inboundIds": [inbound_result["inbound_id"]]
        }
        result = await self._request_json(
            "POST",
            "/panel/api/clients/add",
            payload=payload
        )

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "client": None
            }

        return await self._verify_client_state(
            email=email,
            devices=devices,
            expiry_time_ms=expiry_time_ms
        )

    async def update_client(
        self,
        *,
        client: dict,
        devices: int,
        expiry_time_ms: int
    ):
        email = str(client.get("email"))
        telegram_id = client.get("tg_id", 0)

        if not telegram_id and email.isdigit():
            telegram_id = int(email)

        if self.provisioning_inbound_ids:
            return await self._sync_client_across_inbounds(
                email=email,
                telegram_id=telegram_id,
                devices=devices,
                expiry_time_ms=expiry_time_ms,
                existing_client=client
            )

        payload = {
            "id": client.get("id", ""),
            "security": client.get("security", ""),
            "password": client.get("password", ""),
            "flow": client.get("flow", ""),
            "auth": client.get("auth", ""),
            "email": email,
            "limitIp": devices,
            "totalGB": client.get("total_gb", 0),
            "expiryTime": expiry_time_ms,
            "enable": True,
            "tgId": telegram_id,
            "subId": client.get("sub_id", ""),
            "comment": client.get("comment", ""),
            "reset": client.get("reset", 0),
            "created_at": client.get("created_at", 0)
        }
        result = await self._request_json(
            "POST",
            f"/panel/api/clients/update/{quote(email, safe='')}",
            payload=payload
        )

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "client": None
            }

        return await self._verify_client_state(
            email=email,
            devices=devices,
            expiry_time_ms=expiry_time_ms
        )

    async def _verify_client_state_across_inbounds(
        self,
        *,
        email: str,
        devices: int,
        expiry_time_ms: int,
        inbound_ids: list[int]
    ):
        result = await self.get_all_clients()

        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "client": None
            }

        clients = [
            client
            for client in result["clients"]
            if (
                str(client.get("email")) == str(email)
                and client.get("inbound_id") in set(inbound_ids)
            )
        ]
        found_inbound_ids = {client.get("inbound_id") for client in clients}
        missing_inbound_ids = set(inbound_ids) - found_inbound_ids

        if missing_inbound_ids:
            return {
                "success": False,
                "error": (
                    "3X-UI РЅРµ СЃРѕР·РґР°Р» РєР»РёРµРЅС‚Р° РІ inbound: "
                    f"{', '.join(str(item) for item in sorted(missing_inbound_ids))}"
                ),
                "client": None
            }

        invalid_clients = [
            client
            for client in clients
            if (
                not client.get("enable")
                or client.get("limit_ip") != devices
                or client.get("expiry_time") != expiry_time_ms
            )
        ]

        if invalid_clients:
            return {
                "success": False,
                "error": "3X-UI РЅРµ РїСЂРёРјРµРЅРёР» РїР°СЂР°РјРµС‚СЂС‹ РІРѕ РІСЃРµС… inbound",
                "client": invalid_clients[0]
            }

        primary_client = next(
            (
                client
                for client in clients
                if client.get("inbound_id") == inbound_ids[0]
            ),
            clients[0]
        )

        return {
            "success": True,
            "error": None,
            "client": primary_client
        }

    async def _verify_client_state(
        self,
        *,
        email: str,
        devices: int,
        expiry_time_ms: int
    ):
        result = await self.get_client_by_email(email)

        if not result["success"]:
            return result

        client = result["client"]

        if not client:
            return {
                "success": False,
                "error": "Клиент не найден после операции 3X-UI",
                "client": None
            }

        if (
            not client.get("enable")
            or client.get("limit_ip") != devices
            or client.get("expiry_time") != expiry_time_ms
        ):
            return {
                "success": False,
                "error": "3X-UI не применил параметры подписки",
                "client": client
            }

        return {
            "success": True,
            "error": None,
            "client": client
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
