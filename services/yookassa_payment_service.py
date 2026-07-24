from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import uuid4

from aiohttp import BasicAuth, ClientSession, ClientTimeout

from config import (
    YOOKASSA_RETURN_URL,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)
from database import (
    claim_yookassa_payment,
    complete_order,
    create_yookassa_order,
    fail_order,
    get_order,
)
from services.subscription_service import (
    SubscriptionService,
    calculate_target_expiry_ms,
)
from services.tariff_service import Tariff


API_URL = "https://api.yookassa.ru/v3/payments"


class YooKassaPaymentService:
    def __init__(
        self,
        subscription_service: SubscriptionService | None = None,
    ) -> None:
        self.subscription_service = (
            subscription_service or SubscriptionService()
        )

    @property
    def is_configured(self) -> bool:
        return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)

    def create_order(
        self,
        *,
        telegram_id: int,
        tariff: Tariff,
        purchase_result: dict,
    ) -> dict:
        client = purchase_result.get("client")
        current_expiry_ms = (
            client.get("expiry_time") if client else None
        )
        target_expiry_ms = calculate_target_expiry_ms(
            current_expiry_ms,
            tariff.duration_days,
        )
        order_id = create_yookassa_order(
            telegram_id=telegram_id,
            tariff_code=tariff.code,
            devices=tariff.devices,
            duration_days=tariff.duration_days,
            action=purchase_result["action"],
            target_expiry_ms=target_expiry_ms,
            payment_amount=tariff.price_rub,
        )
        return get_order(order_id)

    async def create_payment(self, order: dict) -> str:
        if not self.is_configured:
            raise RuntimeError("YooKassa is not configured")

        payload = {
            "amount": {
                "value": self._amount_text(order["payment_amount"]),
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": YOOKASSA_RETURN_URL,
            },
            "description": (
                f"CosmoNet VPN: {order['tariff_code']} (order #{order['id']})"
            ),
            "metadata": {"order_id": str(order["id"])},
        }

        try:
            response = await self._request("POST", API_URL, payload)
            payment_url = response.get("confirmation", {}).get(
                "confirmation_url"
            )
            if not response.get("id") or not isinstance(payment_url, str):
                raise RuntimeError("YooKassa did not return a payment URL")
            return payment_url
        except RuntimeError as error:
            fail_order(order["id"], str(error))
            raise

    async def process_notification(self, payload: dict) -> dict:
        if payload.get("event") != "payment.succeeded":
            return self._error("ignored", "Unsupported YooKassa event")

        notification = payload.get("object")
        if not isinstance(notification, dict):
            return self._error("invalid", "Invalid YooKassa notification")

        payment_id = notification.get("id")
        if not isinstance(payment_id, str) or not payment_id:
            return self._error("invalid", "Invalid YooKassa payment id")

        try:
            payment = await self._request("GET", f"{API_URL}/{payment_id}")
        except RuntimeError as error:
            return self._error("invalid", str(error))

        metadata = payment.get("metadata")
        raw_order_id = metadata.get("order_id") if isinstance(metadata, dict) else None
        try:
            order_id = int(raw_order_id)
            amount = Decimal(str(payment.get("amount", {}).get("value", "")))
        except (TypeError, ValueError, InvalidOperation):
            return self._error("invalid", "Invalid YooKassa payment data")

        order = get_order(order_id)
        if (
            not order
            or payment.get("status") != "succeeded"
            or payment.get("paid") is not True
            or payment.get("amount", {}).get("currency") != "RUB"
            or Decimal(order["payment_amount"]) != amount
        ):
            return self._error("invalid", "YooKassa payment does not match an order")

        claim_status, order = claim_yookassa_payment(
            order_id=order_id,
            payment_id=payment_id,
        )
        if claim_status == "already_paid":
            return {
                "success": True,
                "status": "already_paid",
                "error": None,
                "order": order,
                "client": None,
            }
        if claim_status != "claimed":
            return self._error(
                claim_status,
                "YooKassa payment is already being processed",
                order,
            )
        return await self._provision(order)

    async def _request(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
    ) -> dict:
        headers = {"Idempotence-Key": str(uuid4())}
        timeout = ClientTimeout(total=20)
        auth = BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        async with ClientSession(timeout=timeout, auth=auth) as session:
            async with session.request(
                method,
                url,
                json=payload,
                headers=headers,
            ) as response:
                try:
                    data = await response.json(content_type=None)
                except ValueError:
                    data = {}

                if response.status not in {200, 201}:
                    description = data.get("description") if isinstance(data, dict) else None
                    raise RuntimeError(
                        f"YooKassa API error {response.status}: "
                        f"{description or 'unknown error'}"
                    )
                if not isinstance(data, dict):
                    raise RuntimeError("Invalid YooKassa API response")
                return data

    async def _provision(self, order: dict) -> dict:
        result = await self.subscription_service.provision_subscription(
            telegram_id=order["telegram_id"],
            devices=order["devices"],
            target_expiry_ms=order["target_expiry_ms"],
        )
        if not result["success"]:
            error = str(result["error"])
            fail_order(order["id"], error)
            return self._error(
                "provisioning_failed",
                error,
                get_order(order["id"]),
                result.get("client"),
            )

        complete_order(order["id"])
        return {
            "success": True,
            "status": "paid",
            "error": None,
            "order": get_order(order["id"]),
            "client": result["client"],
        }

    @staticmethod
    def _amount_text(value: int | Decimal) -> str:
        return f"{Decimal(value):.2f}"

    @staticmethod
    def _error(
        status: str,
        error: str,
        order: dict | None = None,
        client: dict | None = None,
    ) -> dict:
        return {
            "success": False,
            "status": status,
            "error": error,
            "order": order,
            "client": client,
        }
