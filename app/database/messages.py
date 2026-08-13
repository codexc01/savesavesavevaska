"""Database operations for MessageModel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import MediaMetadataModel, MessageModel, MessageVersionModel


async def save_message(
    session: AsyncSession,
    business_connection_id: str,
    chat_id: int,
    message_id: int,
    sender_id: int,
    date: datetime,
    message_type: str,
    category: str = "TEXT",
    sender_name: str | None = None,
    sender_username: str | None = None,
    text: str | None = None,
    caption: str | None = None,
    file_id: str | None = None,
    file_unique_id: str | None = None,
    local_file_path: str | None = None,
    media_group_id: str | None = None,
    reply_to_message_id: int | None = None,
    raw_metadata: dict[str, Any] | None = None,
) -> tuple[MessageModel, bool]:
    """Save a new incoming business message (idempotent)."""
    stmt = select(MessageModel).where(
        MessageModel.business_connection_id == business_connection_id,
        MessageModel.chat_id == chat_id,
        MessageModel.message_id == message_id,
    )
    res = await session.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing is not None:
        return existing, False

    msg = MessageModel(
        business_connection_id=business_connection_id,
        chat_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        sender_username=sender_username,
        date=date,
        message_type=message_type,
        category=category,
        text=text,
        caption=caption,
        file_id=file_id,
        file_unique_id=file_unique_id,
        local_file_path=local_file_path,
        media_group_id=media_group_id,
        reply_to_message_id=reply_to_message_id,
        raw_metadata=raw_metadata,
    )
    session.add(msg)
    await session.flush()

    # Initial version v1
    v1 = MessageVersionModel(
        message_pk=msg.id,
        version_number=1,
        text=text,
        caption=caption,
        file_id=file_id,
    )
    session.add(v1)

    # Attach MediaMetadata if file_id is present
    if file_id:
        media = MediaMetadataModel(
            message_pk=msg.id,
            file_id=file_id,
            file_unique_id=file_unique_id,
        )
        session.add(media)

    await session.flush()
    return msg, True


async def get_message(
    session: AsyncSession, business_connection_id: str, chat_id: int, message_id: int
) -> MessageModel | None:
    """Retrieve message by business connection, chat, and message ID."""
    stmt = (
        select(MessageModel)
        .options(
            selectinload(MessageModel.versions),
            selectinload(MessageModel.media_item),
        )
        .where(
            MessageModel.business_connection_id == business_connection_id,
            MessageModel.chat_id == chat_id,
            MessageModel.message_id == message_id,
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


get_message_by_chat_and_id = get_message


async def mark_message_deleted(
    session: AsyncSession, business_connection_id: str, chat_id: int, message_id: int
) -> MessageModel | None:
    """Mark a message as deleted."""
    msg = await get_message(session, business_connection_id, chat_id, message_id)
    if msg and not msg.is_deleted:
        msg.is_deleted = True
        msg.deleted_at = datetime.now(timezone.utc)
        await session.flush()
    return msg
