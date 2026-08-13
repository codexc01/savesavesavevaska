"""Edited Business Messages handler — Phase 8.

Receives edited_business_message update from Telegram, retrieves previous version
from database, saves new version (v2, v3...), and notifies the user with diff:
  - Было (Old content)
  - Стало (New content)
"""

from __future__ import annotations

import structlog
from aiogram import Bot, Router
from aiogram.types import Message

from app.database.connections import get_business_connection
from app.database.edits import record_message_edit
from app.database.models import MessageModel, MessageVersionModel
from app.database.session import get_db_session
from app.services.archive import archive_business_message

logger = structlog.get_logger(__name__)
router = Router(name="edited")


def _format_edit_notification(
    msg: MessageModel, prev_version: MessageVersionModel, new_version: MessageVersionModel
) -> str:
    """Format edited message diff header and before/after body without time."""
    name = msg.sender_name or "Собеседник"
    if msg.sender_username:
        user_link = f'<a href="https://t.me/{msg.sender_username}">{name}</a>'
    elif msg.sender_id:
        user_link = f'<a href="tg://user?id={msg.sender_id}">{name}</a>'
    else:
        user_link = f"<b>{name}</b>"

    old_content = prev_version.text or prev_version.caption or "[Медиа/Пусто]"
    new_content = new_version.text or new_version.caption or "[Медиа/Пусто]"

    body = (
        "✏️ <b>Изменённое сообщение</b>\n\n"
        f"👤 {user_link}\n\n"
        f"<b>Было:</b>\n{old_content}\n\n"
        f"<b>Стало:</b>\n{new_content}"
    )

    return body


@router.edited_business_message()
async def on_edited_business_message(msg: Message, bot: Bot) -> None:
    """Handle edited_business_message update."""
    conn_id = msg.business_connection_id
    if not conn_id:
        return

    chat_id = msg.chat.id
    message_id = msg.message_id

    new_text = msg.text
    new_caption = msg.caption

    # Determine file_id if present
    new_file_id = None
    if msg.photo:
        new_file_id = msg.photo[-1].file_id
    elif msg.video:
        new_file_id = msg.video.file_id
    elif msg.animation:
        new_file_id = msg.animation.file_id
    elif msg.document:
        new_file_id = msg.document.file_id

    async with get_db_session() as session:
        # Record edit version into DB
        db_msg, new_version = await record_message_edit(
            session=session,
            business_connection_id=conn_id,
            chat_id=chat_id,
            message_id=message_id,
            new_text=new_text,
            new_caption=new_caption,
            new_file_id=new_file_id,
        )

        # If message was not cached previously, archive it as initial state first
        if db_msg is None:
            db_msg, _ = await archive_business_message(session, msg)
            logger.debug(
                "Edited message was not found in cache, created initial record",
                conn_id=conn_id[:8] + "...",
                chat_id=chat_id,
                msg_id=message_id,
            )
            return

        # If content didn't change (duplicate edit update), do nothing
        if new_version is None:
            return

        # Retrieve previous version for diff
        versions = db_msg.versions
        prev_version = None
        for v in reversed(versions):
            if v.version_number < new_version.version_number:
                prev_version = v
                break

        if prev_version is None:
            return

        # Send edit notification to user
        from app.config import get_settings
        conn = await get_business_connection(session, conn_id)
        target_chat_id = conn.user_chat_id if conn else get_settings().admin_id

        text_notice = _format_edit_notification(db_msg, prev_version, new_version)

        try:
            await bot.send_message(
                chat_id=target_chat_id,
                text=text_notice,
            )
            logger.info(
                "Edited business message notification sent",
                conn_id=conn_id[:8] + "...",
                chat_id=chat_id,
                msg_id=message_id,
                version=new_version.version_number,
            )
        except Exception as exc:
            logger.error(
                "Failed to send edit notification",
                conn_id=conn_id[:8] + "...",
                chat_id=chat_id,
                msg_id=message_id,
                error=str(exc),
            )
