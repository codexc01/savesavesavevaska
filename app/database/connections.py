"""Database operations for BusinessConnectionModel."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BusinessConnectionModel


async def upsert_business_connection(
    session: AsyncSession,
    business_connection_id: str,
    user_id: int,
    user_chat_id: int,
    is_enabled: bool,
    rights: dict[str, Any] | None = None,
    username: str | None = None,
    first_name: str | None = None,
) -> tuple[BusinessConnectionModel, bool]:
    """Insert or update a business connection record.

    When user reconnects (is_enabled=True), purges any stale/disconnected records for the user.
    """
    if is_enabled:
        # Purge any old disabled records for this user_id
        purge_stmt = delete(BusinessConnectionModel).where(
            BusinessConnectionModel.user_id == user_id,
            BusinessConnectionModel.business_connection_id != business_connection_id,
        )
        await session.execute(purge_stmt)

    stmt = select(BusinessConnectionModel).where(
        BusinessConnectionModel.business_connection_id == business_connection_id
    )
    res = await session.execute(stmt)
    conn = res.scalar_one_or_none()

    if conn is None:
        conn = BusinessConnectionModel(
            business_connection_id=business_connection_id,
            user_id=user_id,
            user_chat_id=user_chat_id,
            is_enabled=is_enabled,
            rights=rights,
            username=username,
            first_name=first_name,
        )
        session.add(conn)
        await session.flush()
        return conn, True

    conn.is_enabled = is_enabled
    conn.user_chat_id = user_chat_id
    conn.rights = rights
    if username is not None:
        conn.username = username
    if first_name is not None:
        conn.first_name = first_name

    if not is_enabled:
        from datetime import datetime, timezone
        conn.disconnected_at = datetime.now(timezone.utc)

    await session.flush()
    return conn, False


async def get_business_connection(
    session: AsyncSession, business_connection_id: str
) -> BusinessConnectionModel | None:
    """Retrieve a single business connection by its ID."""
    stmt = select(BusinessConnectionModel).where(
        BusinessConnectionModel.business_connection_id == business_connection_id
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_business_connections(
    session: AsyncSession, active_only: bool = False
) -> list[BusinessConnectionModel]:
    """Retrieve business connections (default active_only=True to hide unlinked accounts)."""
    stmt = select(BusinessConnectionModel)
    if active_only:
        stmt = stmt.where(BusinessConnectionModel.is_enabled.is_(True))
    stmt = stmt.order_by(BusinessConnectionModel.connected_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def is_user_banned(session: AsyncSession, user_id: int) -> bool:
    """Check if a user_id is banned by admin."""
    from app.database.models import BannedUserModel
    stmt = select(BannedUserModel).where(BannedUserModel.user_id == user_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def ban_and_remove_user(
    session: AsyncSession, user_id: int, username: str | None = None
) -> None:
    """Ban a user and delete all their active business connection records and cached messages."""
    from app.database.models import BannedUserModel

    # Add to banned table
    if not await is_user_banned(session, user_id):
        banned = BannedUserModel(user_id=user_id, username=username)
        session.add(banned)

    # Delete connection records (cascade deletes saved messages)
    del_stmt = delete(BusinessConnectionModel).where(
        BusinessConnectionModel.user_id == user_id
    )
    await session.execute(del_stmt)
    await session.flush()
