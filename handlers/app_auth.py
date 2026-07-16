from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import add_user_if_not_exists
from services.app_auth_service import AppAuthService


router = Router()


def _register_user(message: Message) -> None:
    user = message.from_user
    add_user_if_not_exists(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )


@router.message(CommandStart(deep_link=True))
async def telegram_auth_start(message: Message) -> None:
    payload = (message.text or "").partition(" ")[2]
    if not payload.startswith("auth_"):
        return

    session_id = payload.removeprefix("auth_")
    if not AppAuthService().get_pending_session(session_id):
        await message.answer("Сессия входа истекла. Вернитесь в приложение и начните заново.")
        return

    _register_user(message)
    await message.answer(
        "Подтвердить вход в CosmoNet для этого устройства?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Подтвердить вход",
                callback_data=f"app_auth:approve:{session_id}",
            ),
            InlineKeyboardButton(
                text="✖️ Отклонить",
                callback_data=f"app_auth:reject:{session_id}",
            ),
        ]]),
    )


@router.callback_query(F.data.startswith("app_auth:"))
async def telegram_auth_callback(callback: CallbackQuery) -> None:
    _, action, session_id = (callback.data or "").split(":", 2)
    service = AppAuthService()

    if action == "approve":
        user = callback.from_user
        add_user_if_not_exists(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )
        approved = service.approve_session(
            session_id=session_id,
            telegram_id=user.id,
            display_name=user.full_name or user.username or "Telegram",
        )
        text = (
            "✅ Вход в CosmoNet подтвержден. Вернитесь в приложение."
            if approved else "Сессия входа уже истекла или была обработана."
        )
    else:
        rejected = action == "reject" and service.reject_session(
            session_id=session_id,
            telegram_id=callback.from_user.id,
        )
        text = (
            "Вход в CosmoNet отклонен."
            if rejected else "Сессия входа уже истекла или была обработана."
        )

    await callback.answer(text)
    if callback.message:
        await callback.message.edit_text(text)