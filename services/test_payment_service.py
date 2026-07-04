from database import (
    claim_test_order,
    complete_order,
    create_test_order,
    fail_order,
    get_order,
)
from services.subscription_service import (
    SubscriptionService,
    calculate_target_expiry_ms,
)
from services.tariff_service import Tariff


class TestPaymentService:
    def __init__(
        self,
        subscription_service: SubscriptionService | None = None
    ):
        self.subscription_service = (
            subscription_service
            or SubscriptionService()
        )

    @staticmethod
    def get_order(order_id: int):
        return get_order(order_id)

    def create_order(
        self,
        *,
        telegram_id: int,
        tariff: Tariff,
        purchase_result: dict
    ):
        client = purchase_result.get("client")
        current_expiry_ms = (
            client.get("expiry_time")
            if client
            else None
        )
        target_expiry_ms = calculate_target_expiry_ms(
            current_expiry_ms,
            tariff.duration_days
        )
        order_id = create_test_order(
            telegram_id=telegram_id,
            tariff_code=tariff.code,
            devices=tariff.devices,
            duration_days=tariff.duration_days,
            action=purchase_result["action"],
            target_expiry_ms=target_expiry_ms
        )
        return get_order(order_id)

    async def confirm_order(self, order_id: int):
        existing_order = get_order(order_id)

        if not existing_order:
            return {
                "success": False,
                "status": "not_found",
                "error": "Тестовый заказ не найден",
                "order": None,
                "client": None
            }

        if existing_order["status"] == "paid":
            client_result = (
                await self.subscription_service.get_user_vpn_client(
                    existing_order["telegram_id"]
                )
            )
            return {
                "success": True,
                "status": "already_paid",
                "error": None,
                "order": existing_order,
                "client": (
                    client_result.get("client")
                    if client_result["success"]
                    else None
                )
            }

        order = claim_test_order(order_id)

        if not order:
            return {
                "success": False,
                "status": "processing",
                "error": "Заказ уже обрабатывается",
                "order": existing_order,
                "client": None
            }

        result = await self.subscription_service.provision_subscription(
            telegram_id=order["telegram_id"],
            devices=order["devices"],
            target_expiry_ms=order["target_expiry_ms"]
        )

        if not result["success"]:
            error = str(result["error"])
            fail_order(order_id, error)
            return {
                "success": False,
                "status": "failed",
                "error": error,
                "order": get_order(order_id),
                "client": result.get("client")
            }

        complete_order(order_id)
        return {
            "success": True,
            "status": "paid",
            "error": None,
            "order": get_order(order_id),
            "client": result["client"]
        }
