from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from html import escape
from time import monotonic
from typing import Any, Iterable

from aiohttp import web
from aiogram import Bot

from config import ADMIN_IDS, BOT_USERNAME, XUI_SUB_BASE_URL
from services.app_auth_service import AppAuthService
from services.subscription_service import SubscriptionService
from services.tariff_service import get_tariff_by_code, get_tariff_for_user
from services.yookassa_payment_service import YooKassaPaymentService
from services.xui_service import XUIService


def _ru(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


MAX_REQUESTS_PER_WINDOW = 3
RATE_LIMIT_WINDOW_SECONDS = 600


@dataclass(frozen=True)
class FeedbackPayload:
    name: str
    contacts: str
    message: str


class FeedbackRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, client_key: str) -> bool:
        now = monotonic()
        requests = self._requests[client_key]
        while requests and now - requests[0] >= RATE_LIMIT_WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= MAX_REQUESTS_PER_WINDOW:
            return False
        requests.append(now)
        return True


def parse_feedback_payload(data: Any) -> FeedbackPayload:
    if not isinstance(data, dict):
        raise ValueError("Ожидается JSON-объект.")
    return FeedbackPayload(
        name=_required_text(data, "name", 100),
        contacts=_required_text(data, "contacts", 300),
        message=_required_text(data, "message", 3000),
    )


def format_feedback_message(payload: FeedbackPayload) -> str:
    return (
        "<b>Новое обращение из CosmoNet</b>\n\n"
        f"<b>Имя:</b> {escape(payload.name)}\n"
        f"<b>Контакт:</b> {escape(payload.contacts)}\n\n"
        f"<b>Обращение:</b>\n{escape(payload.message)}"
    )


async def deliver_feedback(
    bot: Bot,
    admin_ids: Iterable[int],
    payload: FeedbackPayload,
) -> int:
    delivered = 0
    text = format_feedback_message(payload)
    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
            delivered += 1
        except Exception:
            continue
    return delivered


def create_app(
    bot: Bot,
    xui_service: XUIService | None = None,
    auth_service: AppAuthService | None = None,
    yookassa_service: YooKassaPaymentService | None = None,
    bot_username: str | None = None,
) -> web.Application:
    app = web.Application(client_max_size=16 * 1024)
    rate_limiter = FeedbackRateLimiter()
    xui = xui_service or XUIService()
    auth = auth_service or AppAuthService()
    yookassa = yookassa_service or YooKassaPaymentService(
        SubscriptionService(xui)
    )
    telegram_username = (bot_username if bot_username is not None else BOT_USERNAME).lstrip("@").strip()

    async def submit_feedback(request: web.Request) -> web.Response:
        client_key = request.remote or "unknown"
        if not rate_limiter.allow(client_key):
            return web.json_response({"message": "Слишком много обращений. Попробуйте позже."}, status=429)
        try:
            payload = parse_feedback_payload(await request.json())
        except (ValueError, web.HTTPException):
            return web.json_response({"message": "Проверьте заполнение полей."}, status=400)

        delivered = await deliver_feedback(bot, _configured_admin_ids(), payload)
        if delivered == 0:
            return web.json_response({"message": "Сервис временно недоступен."}, status=503)
        return web.json_response({"delivered": True})


    async def yookassa_result(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except (ValueError, web.HTTPException):
            return web.json_response({"accepted": False}, status=400)

        result = await yookassa.process_notification(payload)
        if result.get("status") in {"paid", "provisioning_failed"}:
            await _notify_yookassa_result(bot, result)
        return web.json_response({"accepted": True})

    async def yookassa_return(_: web.Request) -> web.Response:
        return web.Response(
            text=_ru(r"<h1>\u041e\u043f\u043b\u0430\u0442\u0430 \u043e\u0431\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442\u0441\u044f</h1><p>\u0412\u0435\u0440\u043d\u0438\u0442\u0435\u0441\u044c \u0432 Telegram-\u0431\u043e\u0442: \u0434\u043e\u0441\u0442\u0443\u043f \u0431\u0443\u0434\u0435\u0442 \u0432\u044b\u0434\u0430\u043d \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u043f\u043b\u0430\u0442\u0435\u0436\u0430.</p>"),
            content_type="text/html",
        )

    async def start_auth(request: web.Request) -> web.Response:
        if not telegram_username:
            return web.json_response({"message": "Telegram bot username is not configured."}, status=503)
        try:
            data = await request.json()
            device_id = _required_text(data, "deviceId", 128)
            device_name = _optional_text(data, "deviceName", 128)
            platform = _optional_text(data, "platform", 64)
        except (ValueError, web.HTTPException):
            return web.json_response({"message": "Invalid authorization request."}, status=400)

        session = auth.create_login_session(
            device_id=device_id,
            device_name=device_name,
            platform=platform,
        )
        session_id = session["sessionId"]
        return web.json_response({
            **session,
            "telegramDeepLink": f"https://t.me/{telegram_username}?start=auth_{session_id}",
        })

    async def auth_status(request: web.Request) -> web.Response:
        device_id = request.query.get("deviceId", "").strip()
        session_id = request.query.get("sessionId", "").strip()
        if not device_id or not session_id:
            return web.json_response({"message": "Authorization session is required."}, status=400)

        result = auth.get_status(device_id=device_id, session_id=session_id)
        if not result["isAuthorized"]:
            return web.json_response(result)

        try:
            result.update(await _subscription_payload(xui, int(result["telegramId"])))
        except RuntimeError:
            return web.json_response({"message": "3X-UI is unavailable."}, status=503)
        return web.json_response(result)

    async def get_subscription(request: web.Request) -> web.Response:
        token = _bearer_token(request)
        owner = auth.get_token_owner(token) if token else None
        if not owner:
            return web.json_response({"message": "Unauthorized."}, status=401)
        try:
            return web.json_response(
                await _subscription_payload(xui, int(owner["telegram_id"]))
            )
        except RuntimeError:
            return web.json_response({"message": "3X-UI is unavailable."}, status=503)

    async def create_yookassa_payment(request: web.Request) -> web.Response:
        token = _bearer_token(request)
        owner = auth.get_token_owner(token) if token else None
        if not owner:
            return web.json_response({"message": "Unauthorized."}, status=401)
        if not yookassa.is_configured:
            return web.json_response({"message": "Payments are unavailable."}, status=503)

        try:
            data = await request.json()
            tariff_code = _required_text(data, "tariffCode", 32).lower()
            tariff = get_tariff_by_code(tariff_code)
            if not tariff:
                raise ValueError("tariffCode")

            telegram_id = int(owner["telegram_id"])
            purchase_result = await yookassa.subscription_service.get_purchase_action(
                telegram_id
            )
            if not purchase_result.get("success"):
                raise RuntimeError("Subscription service is unavailable.")

            order = yookassa.create_order(
                telegram_id=telegram_id,
                tariff=get_tariff_for_user(telegram_id, tariff),
                purchase_result=purchase_result,
            )
            payment_url = await yookassa.create_payment(order)
        except (ValueError, web.HTTPException):
            return web.json_response({"message": "Invalid payment request."}, status=400)
        except RuntimeError:
            return web.json_response({"message": "Payments are unavailable."}, status=503)

        return web.json_response({
            "orderId": order["id"],
            "paymentUrl": payment_url,
        })

    async def logout(request: web.Request) -> web.Response:
        token = _bearer_token(request)
        if not token or not auth.revoke_token(token):
            return web.json_response({"message": "Unauthorized."}, status=401)
        return web.json_response({"loggedOut": True})

    app.router.add_post("/payments/yookassa/result", yookassa_result)
    app.router.add_get("/payments/yookassa/return", yookassa_return)
    app.router.add_post("/api/app/feedback", submit_feedback)
    app.router.add_post("/api/app/auth/start", start_auth)
    app.router.add_get("/api/app/auth/status", auth_status)
    app.router.add_get("/api/app/subscription", get_subscription)
    app.router.add_post("/api/app/payments/yookassa", create_yookassa_payment)
    app.router.add_post("/api/app/auth/logout", logout)
    return app


async def _subscription_payload(xui: XUIService, telegram_id: int) -> dict[str, Any]:
    result = await xui.get_client_by_email(str(telegram_id))
    if not result["success"]:
        raise RuntimeError(str(result.get("error") or "3X-UI unavailable"))

    client = result["client"]
    if not client:
        return {
            "subscriptionUrl": "",
            "subscription": {
                "status": 0,
                "tariffName": "Подписка не найдена",
                "lastSyncedAt": datetime.now(timezone.utc).isoformat(),
            },
        }

    expiry_ms = _as_positive_int(client.get("expiry_time"))
    expires_at = (
        datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).isoformat()
        if expiry_ms else None
    )
    enabled = client.get("enable") is not False
    status = 4 if not enabled else 1
    if enabled and expiry_ms:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        status = 3 if expiry_ms <= now_ms else 2 if expiry_ms <= now_ms + 3 * 86_400_000 else 1

    sub_id = str(client.get("sub_id") or "")
    base_url = XUI_SUB_BASE_URL.rstrip("/")
    return {
        "subscriptionUrl": f"{base_url}/sub/{sub_id}" if base_url and sub_id else "",
        "subscription": {
            "status": status,
            "tariffName": "CosmoNet",
            "expiresAt": expires_at,
            "deviceLimit": _as_positive_int(client.get("limit_ip")),
            "trafficUsedBytes": _as_positive_int(client.get("up")) + _as_positive_int(client.get("down")),
            "trafficLimitBytes": _as_positive_int(client.get("total_gb")),
            "lastSyncedAt": datetime.now(timezone.utc).isoformat(),
        },
    }


def _bearer_token(request: web.Request) -> str:
    value = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return value[len(prefix):].strip() if value.startswith(prefix) else ""


def _required_text(data: Any, key: str, maximum_length: int) -> str:
    value = _optional_text(data, key, maximum_length)
    if not value:
        raise ValueError(key)
    return value


def _optional_text(data: Any, key: str, maximum_length: int) -> str | None:
    if not isinstance(data, dict):
        raise ValueError(key)
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(key)
    value = value.strip()
    if len(value) > maximum_length:
        raise ValueError(key)
    return value or None


def _as_positive_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0

def _configured_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS", "")
    return [
        int(value.strip())
        for value in raw.split(",")
        if value.strip().isdigit()
    ] or ADMIN_IDS


async def _notify_yookassa_result(bot: Bot, result: dict) -> None:
    order = result["order"]
    if result["status"] == "paid":
        text = (_ru(r"\u2705 <b>\u041e\u043f\u043b\u0430\u0442\u0430 \u043a\u0430\u0440\u0442\u043e\u0439 \u0438\u043b\u0438 \u0421\u0411\u041f \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430</b>\n\n") + _ru(r"\u0417\u0430\u043a\u0430\u0437: ") + f"<code>#{order['id']}</code>\n" + _ru(r"\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0432\u044b\u0434\u0430\u043d\u0430. \u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0440\u0430\u0437\u0434\u0435\u043b \u00ab\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430\u00bb \u0432 \u0431\u043e\u0442\u0435, \u0447\u0442\u043e\u0431\u044b \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043a\u043e\u043d\u0444\u0438\u0433\u0443\u0440\u0430\u0446\u0438\u044e."))
    else:
        text = (_ru(r"\u26a0\ufe0f <b>\u041e\u043f\u043b\u0430\u0442\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0430</b>\n\n") + _ru(r"\u0417\u0430\u043a\u0430\u0437: ") + f"<code>#{order['id']}</code>\n" + _ru(r"\u0412\u044b\u0434\u0430\u0447\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043d\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c. \u041d\u0435 \u043e\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0439\u0442\u0435 \u0437\u0430\u043a\u0430\u0437 \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e \u2014 \u043d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443 \u0447\u0435\u0440\u0435\u0437 /paysupport."))
    try:
        await bot.send_message(chat_id=order["telegram_id"], text=text)
    except Exception:
        pass
