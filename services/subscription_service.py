from datetime import datetime, timezone

from services.xui_service import XUIService


def get_client_email_by_telegram_id(telegram_id: int) -> str:
    return str(telegram_id)


def calculate_target_expiry_ms(
    current_expiry_ms: int | None,
    duration_days: int,
    *,
    now_ms: int | None = None
) -> int:
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    current_expiry_ms = current_expiry_ms or 0
    base_expiry_ms = max(current_expiry_ms, now_ms)
    return base_expiry_ms + duration_days * 24 * 60 * 60 * 1000


class SubscriptionService:
    def __init__(self, xui: XUIService | None = None):
        self.xui = xui or XUIService()

    async def get_user_vpn_client(self, telegram_id: int):
        client_email = get_client_email_by_telegram_id(telegram_id)
        return await self.xui.get_client_by_email(client_email)

    async def get_purchase_action(self, telegram_id: int):
        """
        Логика проекта CosmoNet:

        1. Если пользователя нет в 3X-UI — первая покупка, нужно создать клиента.
        2. Если пользователь уже есть в 3X-UI — новый конфиг не создаём, продлеваем старый.
        """

        result = await self.get_user_vpn_client(telegram_id)

        if not result["success"]:
            return {
                "success": False,
                "action": None,
                "error": result["error"],
                "client": None
            }

        client = result["client"]

        if client:
            return {
                "success": True,
                "action": "renew",
                "error": None,
                "client": client
            }

        return {
            "success": True,
            "action": "create",
            "error": None,
            "client": None
        }

    async def provision_subscription(
        self,
        *,
        telegram_id: int,
        devices: int,
        target_expiry_ms: int
    ):
        result = await self.get_user_vpn_client(telegram_id)

        if not result["success"]:
            return result

        client = result["client"]

        if client:
            return await self.xui.update_client(
                client=client,
                devices=devices,
                expiry_time_ms=target_expiry_ms
            )

        return await self.xui.create_client(
            email=get_client_email_by_telegram_id(telegram_id),
            telegram_id=telegram_id,
            devices=devices,
            expiry_time_ms=target_expiry_ms
        )
