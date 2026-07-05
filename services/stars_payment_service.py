from database import (
    claim_failed_stars_order,
    claim_stars_payment,
    complete_order,
    create_stars_order,
    fail_order,
    get_order,
)
from services.subscription_service import (
    SubscriptionService,
    calculate_target_expiry_ms,
)
from services.tariff_service import Tariff


PAYLOAD_PREFIX = "cosmonet-stars:"


class StarsPaymentService:
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

    @staticmethod
    def parse_order_id(payload: str | None) -> int | None:
        if not payload or not payload.startswith(PAYLOAD_PREFIX):
            return None

        try:
            return int(payload.removeprefix(PAYLOAD_PREFIX))
        except ValueError:
            return None

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
        order_id = create_stars_order(
            telegram_id=telegram_id,
            tariff_code=tariff.code,
            devices=tariff.devices,
            duration_days=tariff.duration_days,
            action=purchase_result["action"],
            target_expiry_ms=target_expiry_ms,
            payment_amount=tariff.price_stars
        )
        return get_order(order_id)

    def validate_checkout(
        self,
        *,
        telegram_id: int,
        payload: str,
        currency: str,
        total_amount: int
    ) -> tuple[bool, str | None]:
        order_id = self.parse_order_id(payload)
        order = get_order(order_id) if order_id is not None else None

        if not order:
            return False, "Заказ не найден. Сформируйте новый счёт."

        if (
            order["provider"] != "telegram_stars"
            or order["telegram_id"] != telegram_id
            or order["invoice_payload"] != payload
            or order["currency"] != currency
            or order["payment_amount"] != total_amount
        ):
            return False, "Параметры платежа не совпадают с заказом."

        if order["status"] != "pending":
            return False, "Этот счёт уже был обработан."

        return True, None

    async def process_payment(
        self,
        *,
        telegram_id: int,
        payload: str,
        currency: str,
        total_amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str
    ):
        order_id = self.parse_order_id(payload)

        if order_id is None:
            return self._error(
                "invalid",
                "Некорректный идентификатор заказа"
            )

        claim_status, order = claim_stars_payment(
            order_id=order_id,
            telegram_id=telegram_id,
            currency=currency,
            total_amount=total_amount,
            telegram_payment_charge_id=telegram_payment_charge_id,
            provider_payment_charge_id=provider_payment_charge_id
        )

        if claim_status == "already_paid":
            client_result = (
                await self.subscription_service.get_user_vpn_client(
                    telegram_id
                )
            )
            return {
                "success": True,
                "status": "already_paid",
                "error": None,
                "order": order,
                "client": (
                    client_result.get("client")
                    if client_result["success"]
                    else None
                )
            }

        if claim_status != "claimed":
            return self._error(
                claim_status,
                (
                    "Платёж уже обрабатывается"
                    if claim_status == "processing"
                    else "Не удалось сопоставить платёж с заказом"
                ),
                order
            )

        return await self._provision(order)

    async def retry_provisioning(
        self,
        *,
        order_id: int,
        telegram_id: int
    ):
        order = claim_failed_stars_order(order_id, telegram_id)

        if not order:
            existing_order = get_order(order_id)

            if (
                existing_order
                and existing_order["telegram_id"] == telegram_id
                and existing_order["status"] == "paid"
            ):
                client_result = (
                    await self.subscription_service.get_user_vpn_client(
                        telegram_id
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

            return self._error(
                "not_retryable",
                "Этот заказ сейчас нельзя повторно обработать",
                existing_order
            )

        return await self._provision(order)

    async def _provision(self, order: dict):
        result = await self.subscription_service.provision_subscription(
            telegram_id=order["telegram_id"],
            devices=order["devices"],
            target_expiry_ms=order["target_expiry_ms"]
        )

        if not result["success"]:
            error = str(result["error"])
            fail_order(order["id"], error)
            return self._error(
                "provisioning_failed",
                error,
                get_order(order["id"]),
                result.get("client")
            )

        complete_order(order["id"])
        return {
            "success": True,
            "status": "paid",
            "error": None,
            "order": get_order(order["id"]),
            "client": result["client"]
        }

    @staticmethod
    def _error(
        status: str,
        error: str,
        order: dict | None = None,
        client: dict | None = None
    ):
        return {
            "success": False,
            "status": status,
            "error": error,
            "order": order,
            "client": client
        }
