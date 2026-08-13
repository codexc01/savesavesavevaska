"""Business message archive service — Phase 6.

Handles metadata extraction and database caching for incoming Telegram Business messages.
Does NOT reply or notify the user on new messages — caches silently for future delete/edit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.messages import save_message
from app.database.models import MessageModel

logger = structlog.get_logger(__name__)


def extract_message_metadata(
    msg: Message, override_conn_id: str | None = None
) -> dict[str, Any]:
    """Extract all relevant metadata from an incoming aiogram Message."""
    # Determine primary file_id and file_unique_id
    file_id: str | None = None
    file_unique_id: str | None = None
    message_type = "text"

    if msg.photo:
        largest = msg.photo[-1]
        file_id = largest.file_id
        file_unique_id = largest.file_unique_id
        message_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        file_unique_id = msg.video.file_unique_id
        message_type = "video"
    elif msg.voice:
        file_id = msg.voice.file_id
        file_unique_id = msg.voice.file_unique_id
        message_type = "voice"
    elif msg.video_note:
        file_id = msg.video_note.file_id
        file_unique_id = msg.video_note.file_unique_id
        message_type = "video_note"
    elif msg.animation:
        file_id = msg.animation.file_id
        file_unique_id = msg.animation.file_unique_id
        message_type = "animation"
    elif msg.audio:
        file_id = msg.audio.file_id
        file_unique_id = msg.audio.file_unique_id
        message_type = "audio"
    elif msg.document:
        file_id = msg.document.file_id
        file_unique_id = msg.document.file_unique_id
        message_type = "document"
    elif msg.sticker:
        file_id = msg.sticker.file_id
        file_unique_id = msg.sticker.file_unique_id
        message_type = "sticker"
    elif msg.text:
        message_type = "text"

    sender_id = msg.from_user.id if msg.from_user else 0
    sender_name = msg.from_user.first_name if msg.from_user else None
    sender_username = msg.from_user.username if msg.from_user else None

    msg_date = msg.date if msg.date else datetime.now(timezone.utc)

    reply_to_id = msg.reply_to_message.message_id if msg.reply_to_message else None

    raw_meta = {
        "has_media_spoiler": msg.has_media_spoiler,
        "has_protected_content": msg.has_protected_content,
    }

    from app.domain.categories import ContentCategory

    category_enum = ContentCategory.classify_message(msg)
    conn_id = override_conn_id or getattr(msg, "business_connection_id", None)

    return {
        "business_connection_id": conn_id,
        "chat_id": msg.chat.id if msg.chat else 0,
        "message_id": msg.message_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "sender_username": sender_username,
        "date": msg_date,
        "message_type": message_type,
        "category": category_enum.value,
        "text": msg.text,
        "caption": msg.caption,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "media_group_id": msg.media_group_id,
        "reply_to_message_id": reply_to_id,
        "raw_metadata": raw_meta,
    }


async def archive_business_message(
    session: AsyncSession,
    msg: Message,
    bot: Bot | None = None,
    override_conn_id: str | None = None,
) -> tuple[MessageModel | None, bool]:
    """Extract metadata, download media locally, and save message into the database."""
    conn_id = override_conn_id or getattr(msg, "business_connection_id", None)
    if not conn_id:
        return None, False

    meta = extract_message_metadata(msg, override_conn_id=conn_id)

    # Download media file to local disk storage if bot instance is available
    local_file_path: str | None = None
    if bot and meta["file_id"]:
        from app.services.media_downloader import download_media_file

        local_file_path = await download_media_file(
            bot, meta["file_id"], meta["file_unique_id"]
        )

    db_msg, created = await save_message(
        session=session,
        business_connection_id=meta["business_connection_id"],
        chat_id=meta["chat_id"],
        message_id=meta["message_id"],
        sender_id=meta["sender_id"],
        date=meta["date"],
        message_type=meta["message_type"],
        category=meta["category"],
        sender_name=meta["sender_name"],
        sender_username=meta["sender_username"],
        text=meta["text"],
        caption=meta["caption"],
        file_id=meta["file_id"],
        file_unique_id=meta["file_unique_id"],
        local_file_path=local_file_path,
        media_group_id=meta["media_group_id"],
        reply_to_message_id=meta["reply_to_message_id"],
        raw_metadata=meta["raw_metadata"],
    )

    from app.services.cache import cache_message_quick

    await cache_message_quick(
        conn_id=meta["business_connection_id"],
        chat_id=meta["chat_id"],
        msg_id=meta["message_id"],
        payload=meta,
    )

    # Archive reply_to_message target if message is a reply (e.g. view-once media)
    reply_target = getattr(msg, "reply_to_message", None)
    if reply_target and not getattr(reply_target, "_archived_reply", False):
        try:
            from contextlib import suppress
            with suppress(Exception):
                object.__setattr__(reply_target, "_archived_reply", True)
            await archive_business_message(
                session, reply_target, bot=bot, override_conn_id=conn_id
            )
        except Exception as exc:
            logger.warning("Could not archive reply_to_message target", error=str(exc))

    return db_msg, created
