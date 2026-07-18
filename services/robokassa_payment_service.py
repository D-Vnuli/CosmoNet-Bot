from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import new as new_hash
from hmac import compare_digest
from urllib.parse import urlencode

from config import (
    ROBOKASSA_HASH_ALGORITHM,
    ROBOKASSA_IS_TEST,
    ROBOKASSA_MERCHANT_LOGIN,
    ROBOKASSA_PASSWORD_1,
    ROBOKASSA_PASSWORD_2,
)
from database import (
    claim_robokassa_payment,
    complete_order,
    create_robokassa_order,
    fail_order,
    get_order,
)
from services.subscription_service import (
    SubscriptionService,
    calculate_target_expiry_ms,
)
from services.tariff_service import Tariff


PAYMENT_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


@dataclass(frozen=True)
class RobokassaSettings:
    merchant_login: str
    password_1: str
    password_2: str
    hash_algorithm: str = "md5"
    is_test: bool = False

    @property
    def configured(self) -> bool:
        return bool(
            self.merchant_login
            and self.password_1
            and self.password_2
        )


class RobokassaPaymentService:
    def __init__(
        self,
        subscription_service: SubscriptionService | None = None,
        settings: RobokassaSettings | None = None,
    ):
        self.subscription_service = (
            subscription_service or SubscriptionService()
        )
        self.settings = settings or RobokassaSettings(
            merchant_login=ROBOKASSA_MERCHANT_LOGIN,
            password_1=ROBOKASSA_PASSWORD_1,
            password_2=ROBOKASSA_PASSWORD_2,
            hash_algorithm=ROBOKASSA_HASH_ALGORITHM,
            is_test=ROBOKASSA_IS_TEST,
        )

    @property
    def is_configured(self) -> bool:
        return self.settings.configured

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
        order_id = create_robokassa_order(
            telegram_id=telegram_id,
            tariff_code=tariff.code,
            devices=tariff.devices,
            duration_days=tariff.duration_days,
            action=purchase_result["action"],
            target_expiry_ms=target_expiry_ms,
            payment_amount=tariff.price_rub,
        )
        return get_order(order_id)

    def payment_url(self, order: dict) -> str:
        if not self.is_configured:
            raise RuntimeError("Robokassa is not configured")

        amount = self._amount_text(order["payment_amount"])
        invoice_id = str(order["id"])
        signature = self._digest(
            f"{self.settings.merchant_login}:{amount}:{invoice_id}:"
            f"{self.settings.password_1}"
        )
        parameters = {
            "MerchantLogin": self.settings.merchant_login,
            "OutSum": amount,
            "InvId": invoice_id,
            "Description": (
                f"CosmoNet VPN subscription: {order['tariff_code']}"
            ),
            "SignatureValue": signature,
            "Culture": "ru",
        }
        if self.settings.is_test:
            parameters["IsTest"] = "1"
        return f"{PAYMENT_URL}?{urlencode(parameters)}"

    async def process_result(self, data: dict[str, str]) -> dict:
        verified, order, error = self.verify_result(data)
        if not verified or not order:
            return self._error("invalid", error or "Invalid notification")

        claim_status, order = claim_robokassa_payment(order["id"])
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
                "Payment is already being processed",
                order,
            )
        return await self._provision(order)

    def verify_result(
        self, data: dict[str, str]
    ) -> tuple[bool, dict | None, str | None]:
        if not self.is_configured:
            return False, None, "Robokassa is not configured"

        try:
            invoice_id = int(data.get("InvId", ""))
            amount = Decimal(data.get("OutSum", ""))
        except (ValueError, InvalidOperation):
            return False, None, "Invalid payment parameters"

        if invoice_id <= 0 or amount < 0:
            return False, None, "Invalid payment parameters"

        order = get_order(invoice_id)
        if (
            not order
            or order["provider"] != "robokassa"
            or Decimal(order["payment_amount"]) != amount
        ):
            return False, None, "Payment does not match an order"

        raw_amount = data.get("OutSum", "")
        signature = data.get("SignatureValue", "")
        expected_signature = self._digest(
            f"{raw_amount}:{invoice_id}:{self.settings.password_2}"
        )
        if not signature or not compare_digest(
            signature.lower(), expected_signature.lower()
        ):
            return False, None, "Invalid payment signature"

        return True, order, None

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

    def _digest(self, value: str) -> str:
        try:
            return new_hash(
                self.settings.hash_algorithm.lower(),
                value.encode("utf-8"),
            ).hexdigest()
        except ValueError as error:
            raise RuntimeError("Unsupported Robokassa hash algorithm") from error

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