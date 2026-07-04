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
                    text = await response.text()

                    try:
                        data = await response.json(content_type=None)
                    except Exception:
                        data = None

                    if not isinstance(data, dict):
                        return {
                            "success": False,
                            "error": (
                                f"3X-UI вернул не JSON. "
                                f"HTTP {response.status}. "
                                f"Ответ: {text[:300]}"
                            ),
                            "inbounds": []
                        }

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