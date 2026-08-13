"""Business message handler — Phase 6.

Receives all incoming business messages and silently caches them into the database.
Does NOT reply to the user or send any copies while the message exists.
"""

from __future__ import annotations

import os
from contextlib import suppress
from typing import Any

import structlog
from aiogram import Bot, Router
from aiogram.types import FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connections import get_business_connection
from app.database.messages import get_message_by_chat_and_id
from app.database.session import get_db_session
from app.services.archive import archive_business_message

logger = structlog.get_logger(__name__)
router = Router(name="messages")


@router.business_message()
async def on_business_message(msg: Message, bot: Bot) -> None:
    """Handle incoming business message update."""
    if not msg.business_connection_id:
        return

    try:
        async with get_db_session() as session:
            await archive_business_message(session, msg, bot=bot)
            await _forward_view_once_media_instantly(bot, session, msg)
            await _forward_reply_media_to_user_chat(bot, session, msg)
    except Exception as exc:
        logger.error(
            "Failed to cache business message",
            conn_id=msg.business_connection_id[:8] + "..."
            if msg.business_connection_id
            else None,
            chat_id=msg.chat.id if msg.chat else None,
            msg_id=msg.message_id,
            error=str(exc),
        )


async def _forward_reply_media_to_user_chat(
    bot: Bot, session: AsyncSession, msg: Message
) -> None:
    """If msg is a reply to media/view-once message, immediately forward to user chat."""
    if not msg.reply_to_message or not msg.business_connection_id:
        return

    reply = msg.reply_to_message
    if not (
        reply.photo
        or reply.video
        or reply.voice
        or reply.video_note
        or reply.animation
        or reply.sticker
        or reply.document
    ):
        return

    if getattr(reply, "_instantly_forwarded", False):
        return

    conn = await get_business_connection(session, msg.business_connection_id)
    if not conn or not conn.user_chat_id:
        return

    db_reply = await get_message_by_chat_and_id(
        session, msg.business_connection_id, reply.chat.id, reply.message_id
    )
    if not db_reply:
        return

    # Check local_file_path or file_id
    media_input: Any = None
    if db_reply.local_file_path and os.path.exists(db_reply.local_file_path):
        media_input = FSInputFile(db_reply.local_file_path)
    elif db_reply.file_id:
        media_input = db_reply.file_id

    if not media_input:
        return

    sender_name = db_reply.sender_name or (
        f"@{db_reply.sender_username}" if db_reply.sender_username else "Собеседник"
    )
    if db_reply.sender_username:
        user_link = f'<a href="https://t.me/{db_reply.sender_username}">{sender_name}</a>'
    elif db_reply.sender_id:
        user_link = f'<a href="tg://user?id={db_reply.sender_id}">{sender_name}</a>'
    else:
        user_link = f"<b>{sender_name}</b>"

    header = f"📸 <b>Сохранённое медиа из твоего ответа:</b>\n👤 {user_link}"

    try:
        if db_reply.message_type == "photo":
            await bot.send_photo(chat_id=conn.user_chat_id, photo=media_input, caption=header)
        elif db_reply.message_type == "video":
            await bot.send_video(chat_id=conn.user_chat_id, video=media_input, caption=header)
        elif db_reply.message_type == "voice":
            await bot.send_voice(chat_id=conn.user_chat_id, voice=media_input, caption=header)
        elif db_reply.message_type == "video_note":
            await bot.send_message(chat_id=conn.user_chat_id, text=header)
            await bot.send_video_note(chat_id=conn.user_chat_id, video_note=media_input)
        elif db_reply.message_type == "animation":
            await bot.send_animation(
                chat_id=conn.user_chat_id, animation=media_input, caption=header
            )
        elif db_reply.message_type == "sticker":
            await bot.send_message(chat_id=conn.user_chat_id, text=header)
            await bot.send_sticker(chat_id=conn.user_chat_id, sticker=media_input)
        elif db_reply.message_type == "document":
            await bot.send_document(
                chat_id=conn.user_chat_id, document=media_input, caption=header
            )

        with suppress(Exception):
            object.__setattr__(reply, "_instantly_forwarded", True)

        logger.info(
            "Instantly forwarded reply target media to user chat",
            conn_id=msg.business_connection_id[:8],
            msg_id=reply.message_id,
        )
    except Exception as exc:
        logger.warning("Could not instantly forward reply target media", error=str(exc))


async def _forward_view_once_media_instantly(
    bot: Bot, session: AsyncSession, msg: Message
) -> None:
    """Instantly forward any View-Once media in business chats directly to bot owner's chat."""
    if not msg.business_connection_id:
        return

    # Check if message has media
    if not (
        msg.photo
        or msg.video
        or msg.voice
        or msg.video_note
        or msg.animation
    ):
        return

    is_view_once = bool(msg.has_protected_content or msg.has_media_spoiler)
    if not is_view_once and not (msg.photo or msg.video or msg.voice or msg.video_note):
        return

    if getattr(msg, "_instantly_vo_forwarded", False):
        return

    conn = await get_business_connection(session, msg.business_connection_id)
    if not conn or not conn.user_chat_id:
        return

    db_msg = await get_message_by_chat_and_id(
        session, msg.business_connection_id, msg.chat.id, msg.message_id
    )
    if not db_msg:
        return

    media_input: Any = None
    if db_msg.local_file_path and os.path.exists(db_msg.local_file_path):
        media_input = FSInputFile(db_msg.local_file_path)
    elif db_msg.file_id:
        media_input = db_msg.file_id

    if not media_input:
        return

    sender_name = db_msg.sender_name or (
        f"@{db_msg.sender_username}" if db_msg.sender_username else "Собеседник"
    )
    if db_msg.sender_username:
        user_link = f'<a href="https://t.me/{db_msg.sender_username}">{sender_name}</a>'
    elif db_msg.sender_id:
        user_link = f'<a href="tg://user?id={db_msg.sender_id}">{sender_name}</a>'
    else:
        user_link = f"<b>{sender_name}</b>"

    header = (
        f"👁‍🗨 <b>Перехвачено одноразовое медиа (View-Once):</b>\n"
        f"👤 {user_link}"
    )

    try:
        if db_msg.message_type == "photo":
            await bot.send_photo(chat_id=conn.user_chat_id, photo=media_input, caption=header)
        elif db_msg.message_type == "video":
            await bot.send_video(chat_id=conn.user_chat_id, video=media_input, caption=header)
        elif db_msg.message_type == "voice":
            await bot.send_voice(chat_id=conn.user_chat_id, voice=media_input, caption=header)
        elif db_msg.message_type == "video_note":
            await bot.send_message(chat_id=conn.user_chat_id, text=header)
            await bot.send_video_note(chat_id=conn.user_chat_id, video_note=media_input)

        with suppress(Exception):
            object.__setattr__(msg, "_instantly_vo_forwarded", True)

        logger.info(
            "Instantly forwarded view-once media to user chat",
            conn_id=msg.business_connection_id[:8],
            msg_id=msg.message_id,
        )
    except Exception as exc:
        logger.warning("Could not instantly forward view-once media", error=str(exc))
