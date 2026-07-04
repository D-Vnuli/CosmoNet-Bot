import asyncio
from dataclasses import dataclass
from enum import Enum

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from database import get_all_telegram_ids
from services.xui_service import XUIService


class BroadcastAudience(str, Enum):
    ALL = "all"
    ACTIVE = "active"
    INACTIVE = "inactive"


class AudienceLoadError(RuntimeError):
    pass


@dataclass
class BroadcastResult:
    total: int
    delivered: int = 0
    unavailable: int = 0
    failed: int = 0


class BroadcastService:
    MAX_ATTEMPTS = 3
    SEND_INTERVAL_SECONDS = 0.05

    def __init__(self):
        self._active_task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._active_task is not None and not self._active_task.done()

    async def resolve_recipients(
        self,
        audience: BroadcastAudience
    ) -> list[int]:
        telegram_ids = list(dict.fromkeys(get_all_telegram_ids()))

        if audience == BroadcastAudience.ALL or not telegram_ids:
            return telegram_ids

        xui = XUIService()
        result = await xui.get_clients_by_emails(telegram_ids)

        if not result["success"]:
            raise AudienceLoadError(str(result["error"]))

        clients = result["clients"]

        if audience == BroadcastAudience.ACTIVE:
            return [
                telegram_id
                for telegram_id in telegram_ids
                if (
                    clients.get(str(telegram_id))
                    and clients[str(telegram_id)].get("enable", False)
                )
            ]

        return [
            telegram_id
            for telegram_id in telegram_ids
            if (
                not clients.get(str(telegram_id))
                or not clients[str(telegram_id)].get("enable", False)
            )
        ]

    def start(
        self,
        *,
        bot: Bot,
        admin_id: int,
        source_chat_id: int,
        source_message_id: int,
        recipient_ids: list[int]
    ) -> bool:
        if self.is_running:
            return False

        self._active_task = asyncio.create_task(
            self._run(
                bot=bot,
                admin_id=admin_id,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                recipient_ids=recipient_ids
            )
        )
        self._active_task.add_done_callback(self._on_task_done)
        return True

    async def wait_until_finished(self):
        task = self._active_task

        if task:
            await task

    def _on_task_done(self, task: asyncio.Task):
        if self._active_task is task:
            self._active_task = None

        if task.cancelled():
            return

        error = task.exception()

        if error:
            print(f"Ошибка фоновой рассылки: {error}")

    async def _run(
        self,
        *,
        bot: Bot,
        admin_id: int,
        source_chat_id: int,
        source_message_id: int,
        recipient_ids: list[int]
    ):
        result = BroadcastResult(total=len(recipient_ids))

        for telegram_id in recipient_ids:
            delivery_status = await self._deliver_message(
                bot=bot,
                telegram_id=telegram_id,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id
            )

            if delivery_status == "delivered":
                result.delivered += 1
            elif delivery_status == "unavailable":
                result.unavailable += 1
            else:
                result.failed += 1

            await asyncio.sleep(self.SEND_INTERVAL_SECONDS)

        await bot.send_message(
            chat_id=admin_id,
            text=(
                "📣 <b>Рассылка завершена</b>\n\n"
                "━━━━━━━━━━━━━━\n\n"
                f"👥 <b>Выбрано адресатов:</b> {result.total}\n"
                f"✅ <b>Доставлено:</b> {result.delivered}\n"
                f"🚫 <b>Бот заблокирован / чат недоступен:</b> "
                f"{result.unavailable}\n"
                f"⚠️ <b>Прочие ошибки:</b> {result.failed}\n\n"
                "━━━━━━━━━━━━━━"
            )
        )

    async def _deliver_message(
        self,
        *,
        bot: Bot,
        telegram_id: int,
        source_chat_id: int,
        source_message_id: int
    ) -> str:
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                await bot.copy_message(
                    chat_id=telegram_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                    protect_content=True
                )
                return "delivered"

            except TelegramRetryAfter as error:
                if attempt == self.MAX_ATTEMPTS:
                    return "failed"

                await asyncio.sleep(error.retry_after)

            except (TelegramForbiddenError, TelegramBadRequest):
                return "unavailable"

            except (TelegramNetworkError, TelegramServerError):
                if attempt == self.MAX_ATTEMPTS:
                    return "failed"

                await asyncio.sleep(min(2 ** (attempt - 1), 5))

            except TelegramAPIError:
                return "failed"

            except Exception:
                return "failed"

        return "failed"


broadcast_service = BroadcastService()
