from services.xui_service import XUIService


def get_client_email_by_telegram_id(telegram_id: int) -> str:
    return str(telegram_id)


class SubscriptionService:
    def __init__(self):
        self.xui = XUIService()

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