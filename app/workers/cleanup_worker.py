"""Periodic background worker for automatic database & media cleanup — Phase 12."""

from __future__ import annotations

import asyncio

import structlog

from app.database.session import get_db_session
from app.services.cleanup import purge_expired_messages

logger = structlog.get_logger(__name__)

# Run cleanup every 6 hours by default
CLEANUP_INTERVAL_SECONDS = 6 * 3600


async def start_cleanup_loop(interval_seconds: int = CLEANUP_INTERVAL_SECONDS) -> None:
    """Infinite periodic loop running retention cleanup in background."""
    logger.info("Starting background retention cleanup worker loop", interval=interval_seconds)

    while True:
        try:
            async with get_db_session() as session:
                stats = await purge_expired_messages(session)
                logger.debug("Cleanup cycle completed", **stats)
        except asyncio.CancelledError:
            logger.info("Background cleanup worker task cancelled")
            break
        except Exception as exc:
            logger.error("Error in background cleanup worker cycle", error=str(exc))

        await asyncio.sleep(interval_seconds)
