"""Media Downloader Service.

Downloads and persists incoming Telegram Business media (Photos, Videos, Voice, Stickers)
to local disk storage (`./storage/media/`) to ensure 100% reliable restoration even if Telegram API
revokes or expires View-Once / Ephemeral file_ids.
"""

from __future__ import annotations

import os
import uuid

import structlog
from aiogram import Bot

logger = structlog.get_logger(__name__)

STORAGE_DIR = os.path.join(os.getcwd(), "storage", "media")


def _ensure_storage_dir() -> None:
    """Ensure media storage directory exists on local disk."""
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)


async def download_media_file(
    bot: Bot, file_id: str, file_unique_id: str | None = None
) -> str | None:
    """Download media file bytes from Telegram API to local storage.

    Returns absolute local file path if successful, None on error.
    """
    if not file_id:
        return None

    _ensure_storage_dir()
    filename = f"{file_unique_id or uuid.uuid4().hex}.bin"
    dest_path = os.path.join(STORAGE_DIR, filename)

    if os.path.exists(dest_path):
        return dest_path

    try:
        file_info = await bot.get_file(file_id)
        if file_info.file_path:
            await bot.download_file(file_info.file_path, destination=dest_path)
            logger.info("Media file cached locally to disk", path=dest_path, file_id=file_id[:12])
            return dest_path
    except Exception as exc:
        logger.warning(
            "Could not download media file locally", file_id=file_id[:12], error=str(exc)
        )

    return None
