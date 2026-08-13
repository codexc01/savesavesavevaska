"""Automatic cleanup & retention policy service — Phase 12.

Purges expired business messages, version history, and temporary media files
older than MESSAGE_CACHE_TTL_DAYS to manage storage cleanly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import MessageModel, MessageVersionModel

logger = structlog.get_logger(__name__)


async def purge_expired_messages(
    session: AsyncSession, ttl_days: int | None = None
) -> dict[str, int]:
    """Purge messages and edit versions older than TTL threshold.

    Returns stats dict: {"messages_deleted": count, "files_removed": count}.
    """
    if ttl_days is None:
        ttl_days = get_settings().message_cache_ttl_days

    threshold = datetime.now(timezone.utc) - timedelta(days=ttl_days)

    # 1. Query expired messages
    stmt = select(MessageModel).where(MessageModel.created_at < threshold)
    res = await session.execute(stmt)
    expired_msgs = list(res.scalars().all())

    if not expired_msgs:
        return {"messages_deleted": 0, "files_removed": 0}

    expired_ids = [msg.id for msg in expired_msgs]

    # 2. Cleanup associated temp disk files if any
    files_removed = 0
    for msg in expired_msgs:
        if msg.local_file_path:
            p_file = Path(msg.local_file_path)
            if p_file.exists() and p_file.is_file():
                try:
                    p_file.unlink()
                    files_removed += 1
                except Exception as exc:
                    logger.warning("Could not unlink local media file", error=str(exc))
        elif msg.file_id:
            temp_dir = Path(get_settings().temp_media_dir)
            if temp_dir.exists():
                potential_file = temp_dir / msg.file_id
                if potential_file.exists() and potential_file.is_file():
                    try:
                        potential_file.unlink()
                        files_removed += 1
                    except Exception as exc:
                        logger.warning(
                            "Could not unlink temp media file",
                            file=str(potential_file),
                            error=str(exc),
                        )

    # 3. Delete version records
    await session.execute(
        delete(MessageVersionModel).where(MessageVersionModel.message_pk.in_(expired_ids))
    )

    # 4. Delete expired message records
    await session.execute(
        delete(MessageModel).where(MessageModel.id.in_(expired_ids))
    )

    await session.flush()

    logger.info(
        "Purged expired messages",
        threshold=threshold.isoformat(),
        messages_deleted=len(expired_ids),
        files_removed=files_removed,
    )

    return {"messages_deleted": len(expired_ids), "files_removed": files_removed}
