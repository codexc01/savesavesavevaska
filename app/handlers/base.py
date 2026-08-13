"""Base handlers — /start, /status.

These are the ONLY user-facing commands at this phase.
Business-specific handlers are added in later phases.
"""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message  # noqa: TCH002

from app.config import get_settings

logger = structlog.get_logger(__name__)
router = Router(name="base")

_settings = get_settings()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Respond to /start — confirms the bot is alive."""
    user = message.from_user
    logger.info(
        "cmd_start",
        user_id=user.id if user else None,
        username=user.username if user else None,
    )
    await message.answer(
        "Привет\n\n"
        "Чтобы подключить бота:\n\n"
        'Подключите по ссылке tg://settings/edit, выберите "Автоматизацию" и введите\n'
        "@deletedavedo_savebot\n"
        "Если не работает - отключите и подключите снова\n\n"
        "После этого бот начнёт сохранять удалённые и изменённые сообщения в твоих чатах"
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Admin-only status command.

    Security: server-side check against ADMIN_ID.
    Even if the command is known, non-admins get a silent denial.
    """
    user = message.from_user
    if not user or user.id != _settings.admin_id:
        logger.warning(
            "Unauthorised /status attempt",
            user_id=user.id if user else None,
        )
        # Silent — don't confirm or deny the command exists
        return

    logger.info("Admin /status", admin_id=user.id)
    await message.answer(
        "🟢 <b>Bot:</b> online\n"
        "⚙️ <b>Mode:</b> " + _settings.bot_mode
    )
