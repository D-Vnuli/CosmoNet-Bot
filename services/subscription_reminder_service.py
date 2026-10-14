from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from database import (
    complete_trial,
    get_active_trials,
    get_trials_pending_notification,
    has_subscription_reminder,
    mark_subscription_reminder_sent,
    mark_trial_expiration_notified,
)
from keyboards.tariff_menu import build_tariff_menu
from services.subscription_service import TRIAL_TRAFFIC_BYTES
from services.xui_service import XUIService, format_expiry_time


class SubscriptionReminderService:
    REMINDER_DAYS = (3, 1)
    DAY_MS = 24 * 60 * 60 * 1000

    def __init__(
        self,
        xui: XUIService | None = None,
        now_ms: Callable[[], int] | None = None
    ):
        self.xui = xui or XUIService()
        self._now_ms = now_ms or self._current_time_ms

    @staticmethod
    def _current_time_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _trial_traffic_usage_bytes(clients: list[dict]) -> int:
        """Sum distinct 3X-UI traffic snapshots for one logical client."""
        used_traffic = 0
        seen_snapshots = set()
        for client in clients:
            up = max(0, client.get("up", 0))
            down = max(0, client.get("down", 0))
            identity = client.get("id") or client.get("sub_id")
            snapshot_key = (
                str(client.get("email")),
                str(identity),
                up,
                down,
            )
            if identity and snapshot_key in seen_snapshots:
                continue
            if identity:
                seen_snapshots.add(snapshot_key)
            used_traffic += up + down
        return used_traffic

    async def send_due_reminders(self, bot: Bot) -> int:
        result = await self.xui.get_all_clients()

        if not result["success"]:
            print(f"Не удалось проверить сроки подписок: {result['error']}")
            return 0

        now_ms = self._now_ms()
        sent_count = 0

        active_trial_ids = {
            trial["telegram_id"]
            for trial in get_active_trials()
        }
        for telegram_id, expiry_time_ms in self._active_clients(
            result["clients"],
            excluded_telegram_ids=active_trial_ids,
        ):
            if expiry_time_ms <= now_ms:
                sent_count += await self._send_reminder(
                    bot,
                    telegram_id,
                    expiry_time_ms,
                    0
                )
                continue

            for days_before in self.REMINDER_DAYS:
                if not self._is_due(
                    expiry_time_ms=expiry_time_ms,
                    days_before=days_before,
                    now_ms=now_ms
                ):
                    continue

                sent_count += await self._send_reminder(
                    bot,
                    telegram_id,
                    expiry_time_ms,
                    days_before
                )

        return sent_count

    async def check_due_trials(self, bot: Bot) -> int:
        trials = get_active_trials()
        pending_notification_ids = get_trials_pending_notification()
        if not trials:
            return await self._send_pending_trial_notifications(
                bot, pending_notification_ids
            )

        result = await self.xui.get_client_records_by_emails(
            [trial["telegram_id"] for trial in trials]
        )
        if not result["success"]:
            print(f"Не удалось проверить пробные периоды: {result['error']}")
            return 0

        now_ms = self._now_ms()
        completed = 0
        for trial in trials:
            telegram_id = trial["telegram_id"]
            clients = result["clients"].get(str(telegram_id), [])
            client = clients[0] if clients else None
            used_traffic = self._trial_traffic_usage_bytes(clients)
            reason = None
            if trial["trial_ends_at"] <= now_ms:
                reason = "time"
            elif used_traffic >= TRIAL_TRAFFIC_BYTES:
                reason = "traffic"
            if not reason:
                continue

            if client:
                disable_result = await self.xui.update_client(
                    client=client,
                    devices=client.get("limit_ip") or 1,
                    expiry_time_ms=client.get("expiry_time") or trial["trial_ends_at"],
                    total_gb=TRIAL_TRAFFIC_BYTES,
                    enabled=False,
                )
                if not disable_result["success"]:
                    print(f"trial_expiration_failed telegram_id={telegram_id}")
                    continue

            if not complete_trial(telegram_id, reason, now_ms):
                continue
            print(f"trial_expired_{reason} telegram_id={telegram_id}")
            completed += await self._notify_trial_expired(bot, telegram_id)
        return completed + await self._send_pending_trial_notifications(
            bot, pending_notification_ids
        )

    async def _send_pending_trial_notifications(
        self,
        bot: Bot,
        telegram_ids: list[int],
    ) -> int:
        sent_count = 0
        for telegram_id in telegram_ids:
            sent_count += await self._notify_trial_expired(bot, telegram_id)
        return sent_count

    async def _notify_trial_expired(self, bot: Bot, telegram_id: int) -> int:
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    "<b>Пробный период CosmoNet закончился.</b>\n\n"
                    "Вы использовали доступный пробный период.\n\n"
                    "Чтобы продолжить пользоваться VPN, выберите один из основных тарифов.\n\n"
                    "Ваша ссылка подписки останется прежней после оплаты."
                ),
                reply_markup=build_tariff_menu(paid_only=True),
            )
        except TelegramForbiddenError:
            mark_trial_expiration_notified(telegram_id)
            return 0
        except TelegramAPIError as error:
            print(f"Не удалось уведомить об окончании trial пользователя {telegram_id}: {error}")
            return 0

        return 1 if mark_trial_expiration_notified(telegram_id) else 0

    async def _send_reminder(
        self,
        bot: Bot,
        telegram_id: int,
        expiry_time_ms: int,
        days_before: int
    ) -> int:
        if has_subscription_reminder(
            telegram_id,
            expiry_time_ms,
            days_before
        ):
            return 0

        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=self._message_text(days_before, expiry_time_ms)
            )
        except TelegramForbiddenError:
            mark_subscription_reminder_sent(
                telegram_id,
                expiry_time_ms,
                days_before
            )
            return 0
        except TelegramAPIError as error:
            print(
                "Не удалось отправить уведомление о подписке "
                f"пользователю {telegram_id}: {error}"
            )
            return 0

        mark_subscription_reminder_sent(
            telegram_id,
            expiry_time_ms,
            days_before
        )
        return 1

    @classmethod
    def _active_clients(
        cls,
        clients: list[dict],
        *,
        excluded_telegram_ids: set[int] | None = None,
    ):
        active_clients: dict[int, int] = {}
        excluded_telegram_ids = excluded_telegram_ids or set()

        for client in clients:
            email = str(client.get("email", ""))
            expiry_time_ms = client.get("expiry_time")

            if (
                not email.isdigit()
                or not client.get("enable")
                or not isinstance(expiry_time_ms, int)
                or expiry_time_ms <= 0
            ):
                continue

            telegram_id = int(email)
            if telegram_id in excluded_telegram_ids:
                continue
            active_clients[telegram_id] = max(
                active_clients.get(telegram_id, 0),
                expiry_time_ms
            )

        return active_clients.items()

    @classmethod
    def _is_due(
        cls,
        *,
        expiry_time_ms: int,
        days_before: int,
        now_ms: int
    ) -> bool:
        remaining_ms = expiry_time_ms - now_ms
        return (
            (days_before - 1) * cls.DAY_MS < remaining_ms
            <= days_before * cls.DAY_MS
        )

    @staticmethod
    def _message_text(days_before: int, expiry_time_ms: int) -> str:
        if days_before == 0:
            return (
                "🔒 <b>Подписка CosmoNet закончилась</b>\n\n"
                f"Доступ к VPN завершён {format_expiry_time(expiry_time_ms)}.\n\n"
                "Чтобы снова пользоваться CosmoNet,\n"
                "нажмите «🚀 Подключиться»."
            )

        days_text = "3 дня" if days_before == 3 else "1 день"
        return (
            "⏳ <b>Подписка CosmoNet скоро закончится</b>\n\n"
            f"До окончания доступа осталось {days_text}.\n"
            f"Подписка действует до: {format_expiry_time(expiry_time_ms)}.\n\n"
            "Чтобы не потерять доступ, продлите подписку в разделе "
            "«🚀 Подключиться»."
        )
