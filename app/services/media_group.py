"""Media Group (Album) handling & grouping service — Phase 9.

Aggregates multiple deleted messages belonging to the same media_group_id into a single
send_media_group call using InputMediaPhoto / InputMediaVideo to prevent spam.
"""

from __future__ import annotations

from collections import defaultdict

import structlog
from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo

from app.database.models import MessageModel

logger = structlog.get_logger(__name__)


def group_deleted_messages(
    messages: list[MessageModel],
) -> tuple[list[MessageModel], dict[str, list[MessageModel]]]:
    """Separate single messages from media group (album) messages.

    Returns:
      - single_messages: list of standalone messages
      - albums: dict mapping media_group_id -> list of album messages
    """
    singles: list[MessageModel] = []
    albums: dict[str, list[MessageModel]] = defaultdict(list)

    for msg in messages:
        if msg.media_group_id:
            albums[msg.media_group_id].append(msg)
        else:
            singles.append(msg)

    # If an album group has only 1 message captured, treat it as a single message
    final_albums: dict[str, list[MessageModel]] = {}
    for group_id, group_msgs in albums.items():
        if len(group_msgs) == 1:
            singles.append(group_msgs[0])
        else:
            # Sort messages by ID for consistent album ordering
            group_msgs.sort(key=lambda m: m.message_id)
            final_albums[group_id] = group_msgs

    return singles, final_albums


async def send_restored_album(
    bot: Bot,
    user_chat_id: int,
    business_connection_id: str,
    album_msgs: list[MessageModel],
    header_text: str,
) -> bool:
    """Send an aggregated media group (album) to the user via send_media_group."""
    media_list: list[InputMediaPhoto | InputMediaVideo] = []

    for idx, msg in enumerate(album_msgs):
        if not msg.file_id:
            continue

        raw_cap = msg.caption or ""
        caption = f"{header_text}\n{raw_cap}".strip() if idx == 0 else (msg.caption or None)

        if msg.message_type == "photo":
            media_list.append(InputMediaPhoto(media=msg.file_id, caption=caption))
        elif msg.message_type == "video":
            media_list.append(InputMediaVideo(media=msg.file_id, caption=caption))

    if not media_list:
        return False

    try:
        await bot.send_media_group(
            chat_id=user_chat_id,
            media=media_list,
        )
        logger.info(
            "Restored media group album sent",
            conn_id=business_connection_id[:8] + "...",
            count=len(media_list),
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to send restored media group album",
            conn_id=business_connection_id[:8] + "...",
            error=str(exc),
        )
        return False
