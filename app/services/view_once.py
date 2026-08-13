"""View-Once / Ephemeral Media handling & limitations protocol — Phase 10.

Telegram API Limitations Protocol:
  - Ephemeral / View-Once media sets `has_protected_content=True` or `has_media_spoiler=True`.
  - Telegram API restricts direct downloading or forwarding of protected media once viewed/expired.
  - If Telegram API denies restoring the raw media bytes, the bot gracefully informs the user
    with an explicit notification rather than failing silently or mocking fake restoration.
"""

from __future__ import annotations

import structlog
from aiogram.types import Message

from app.database.models import MessageModel

logger = structlog.get_logger(__name__)


def is_view_once_candidate(msg: Message | MessageModel) -> bool:
    """Check if a message contains View-Once or Protected Content flags."""
    if isinstance(msg, Message):
        return bool(msg.has_protected_content or msg.has_media_spoiler)

    # For MessageModel, check raw_metadata dict
    raw = msg.raw_metadata or {}
    return bool(raw.get("has_protected_content") or raw.get("has_media_spoiler"))


def format_view_once_notice(msg: MessageModel) -> str:
    """Format clear notification when View-Once media cannot be retrieved due to API Limitation."""
    name = msg.sender_name or "Собеседник"
    if msg.sender_username:
        user_link = f'<a href="https://t.me/{msg.sender_username}">{name}</a>'
    elif msg.sender_id:
        user_link = f'<a href="tg://user?id={msg.sender_id}">{name}</a>'
    else:
        user_link = f"<b>{name}</b>"

    lines = [
        "👁 <b>Исчезающее медиа (View-Once)</b>\n",
        f"👤 {user_link}",
        "",
        "⚠️ <i>Сообщение было отправлено в режиме одноразового просмотра (View-Once). "
        "Telegram API защищает данный контент от автоматического скачивания.</i>",
    ]
    return "\n".join(lines)
