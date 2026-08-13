"""Database operations for message edits & version history."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.messages import get_message
from app.database.models import MessageModel, MessageVersionModel


async def record_message_edit(
    session: AsyncSession,
    business_connection_id: str,
    chat_id: int,
    message_id: int,
    new_text: str | None = None,
    new_caption: str | None = None,
    new_file_id: str | None = None,
) -> tuple[MessageModel | None, MessageVersionModel | None]:
    """Record an edited message version.

    Idempotent: if new content is identical to the latest version, no duplicate version is created.
    """
    msg = await get_message(session, business_connection_id, chat_id, message_id)
    if msg is None:
        return None, None

    # Retrieve all versions ordered
    stmt = (
        select(MessageVersionModel)
        .where(MessageVersionModel.message_pk == msg.id)
        .order_by(MessageVersionModel.version_number.desc())
    )
    res = await session.execute(stmt)
    latest_version = res.scalars().first()

    # Check if identical to latest version
    if latest_version:
        if (
            latest_version.text == new_text
            and latest_version.caption == new_caption
            and latest_version.file_id == new_file_id
        ):
            return msg, None
        next_ver_num = latest_version.version_number + 1
    else:
        next_ver_num = 1

    # Update current state on main message record
    if new_text is not None:
        msg.text = new_text
    if new_caption is not None:
        msg.caption = new_caption
    if new_file_id is not None:
        msg.file_id = new_file_id

    version = MessageVersionModel(
        message_pk=msg.id,
        version_number=next_ver_num,
        text=new_text if new_text is not None else msg.text,
        caption=new_caption if new_caption is not None else msg.caption,
        file_id=new_file_id if new_file_id is not None else msg.file_id,
    )
    session.add(version)
    await session.flush()

    return msg, version


async def get_message_history(
    session: AsyncSession, business_connection_id: str, chat_id: int, message_id: int
) -> list[MessageVersionModel]:
    """Retrieve all historic versions of a message."""
    msg = await get_message(session, business_connection_id, chat_id, message_id)
    if msg is None:
        return []

    stmt = (
        select(MessageVersionModel)
        .where(MessageVersionModel.message_pk == msg.id)
        .order_by(MessageVersionModel.version_number.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
