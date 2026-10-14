from datetime import datetime, timezone

from database import (
    finish_trial_as_paid,
    get_trial_state,
    release_trial_reservation,
    reserve_trial_activation,
)
from services.xui_service import XUIService


TRIAL_DURATION_MS = 24 * 60 * 60 * 1000
TRIAL_TRAFFIC_BYTES = 500 * 1024 * 1024


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
        trial_state = get_trial_state(telegram_id) or {}
        was_active_trial = bool(
            trial_state.get("trial_used")
            and trial_state.get("trial_end_reason") is None
        )
        result = await self.get_user_vpn_client(telegram_id)

        if not result["success"]:
            return result

        client = result["client"]

        if client:
            result = await self.xui.update_client(
                client=client,
                devices=devices,
                expiry_time_ms=target_expiry_ms,
                total_gb=0,
            )
        else:
            result = await self.xui.create_client(
                email=get_client_email_by_telegram_id(telegram_id),
                telegram_id=telegram_id,
                devices=devices,
                expiry_time_ms=target_expiry_ms,
                total_gb=0,
            )
        if result["success"] and result["client"].get("total_gb") != 0:
            return {
                "success": False,
                "error": "3X-UI не снял ограничение трафика пробного периода",
                "client": result["client"],
            }
        if result["success"] and was_active_trial and finish_trial_as_paid(telegram_id):
            print(f"trial_to_paid telegram_id={telegram_id}")
        return result

    async def activate_trial(self, telegram_id: int) -> dict:
        started_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        ends_at_ms = started_at_ms + TRIAL_DURATION_MS
        reservation = reserve_trial_activation(
            telegram_id, started_at_ms, ends_at_ms
        )
        if reservation != "reserved":
            return {
                "success": False,
                "status": reservation,
                "error": None,
                "client": None,
                "ends_at_ms": None,
            }

        print(f"trial_activation_started telegram_id={telegram_id}")
        result = await self.get_user_vpn_client(telegram_id)
        if result["success"]:
            client = result["client"]
            if client:
                result = await self.xui.update_client(
                    client=client,
                    devices=client.get("limit_ip") or 1,
                    expiry_time_ms=ends_at_ms,
                    total_gb=TRIAL_TRAFFIC_BYTES,
                )
            else:
                result = await self.xui.create_client(
                    email=get_client_email_by_telegram_id(telegram_id),
                    telegram_id=telegram_id,
                    devices=1,
                    expiry_time_ms=ends_at_ms,
                    total_gb=TRIAL_TRAFFIC_BYTES,
                )

        if (
            result["success"]
            and result["client"].get("total_gb") != TRIAL_TRAFFIC_BYTES
        ):
            result = {
                "success": False,
                "error": "3X-UI не применил лимит трафика пробного периода",
                "client": result["client"],
            }

        if not result["success"]:
            release_trial_reservation(telegram_id, started_at_ms)
            print(f"trial_activation_failed telegram_id={telegram_id}")
            return {
                "success": False,
                "status": "provisioning_failed",
                "error": result["error"],
                "client": result.get("client"),
                "ends_at_ms": None,
            }

        print(f"trial_activated telegram_id={telegram_id}")
        return {
            "success": True,
            "status": "activated",
            "error": None,
            "client": result["client"],
            "ends_at_ms": ends_at_ms,
        }
