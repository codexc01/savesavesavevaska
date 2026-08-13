"""Deleted Business Messages handler — Phase 7.

Receives deleted_business_messages update from Telegram, retrieves previously cached
messages from database, and sends restored copies back preserving native presentation types:
  - text -> send_message
  - photo -> send_photo
  - video -> send_video
  - voice -> send_voice
  - video_note -> send_video_note
  - animation / GIF -> send_animation
  - audio -> send_audio
  - document -> send_document
  - sticker -> send_sticker
"""

from __future__ import annotations

import structlog
from aiogram import Bot, Router
from aiogram.types import BusinessMessagesDeleted

from app.database.connections import get_business_connection
from app.database.messages import mark_message_deleted
from app.database.models import MessageModel
from app.database.session import get_db_session

logger = structlog.get_logger(__name__)
router = Router(name="deleted")


def _format_header(msg: MessageModel) -> str:
    """Format standard deleted message header block with clickable profile link, without time."""
    name = msg.sender_name or "Собеседник"
    if msg.sender_username:
        user_link = f'<a href="https://t.me/{msg.sender_username}">{name}</a>'
    elif msg.sender_id:
        user_link = f'<a href="tg://user?id={msg.sender_id}">{name}</a>'
    else:
        user_link = f"<b>{name}</b>"

    return f"🗑 <b>Удалённое сообщение</b>\n\n👤 {user_link}\n"


async def send_restored_deleted_message(
    bot: Bot, user_chat_id: int, msg: MessageModel
) -> None:
    """Send restored deleted message preserving native Telegram media type in 1 message."""
    header = _format_header(msg)

    # 1. TEXT
    if msg.message_type == "text" or not msg.file_id:
        body = msg.text or "<i>[Пустое сообщение]</i>"
        full_text = f"{header}\n{body}"
        await bot.send_message(
            chat_id=user_chat_id,
            text=full_text,
        )
        return

    # Prepare caption for media items
    caption_body = msg.caption or msg.text or ""
    caption_text = f"{header}\n{caption_body}".strip() if caption_body else header.strip()

    file_id = msg.file_id
    import os

    from aiogram.types import FSInputFile

    if msg.local_file_path and os.path.exists(msg.local_file_path):
        media_input: str | FSInputFile = FSInputFile(msg.local_file_path)
    else:
        media_input = file_id  # type: ignore[assignment]

    from app.services.view_once import format_view_once_notice, is_view_once_candidate

    try:
        # 2. PHOTO
        if msg.message_type == "photo":
            await bot.send_photo(
                chat_id=user_chat_id,
                photo=media_input,
                caption=caption_text,
            )
        # 3. VIDEO
        elif msg.message_type == "video":
            await bot.send_video(
                chat_id=user_chat_id,
                video=media_input,
                caption=caption_text,
            )
        # 4. VOICE
        elif msg.message_type == "voice":
            await bot.send_voice(
                chat_id=user_chat_id,
                voice=media_input,
                caption=caption_text,
            )
        # 5. VIDEO NOTE (Кружок)
        elif msg.message_type == "video_note":
            await bot.send_video_note(
                chat_id=user_chat_id,
                video_note=media_input,
            )
        # 6. ANIMATION / GIF
        elif msg.message_type == "animation":
            await bot.send_animation(
                chat_id=user_chat_id,
                animation=media_input,
                caption=caption_text,
            )
        # 7. AUDIO
        elif msg.message_type == "audio":
            await bot.send_audio(
                chat_id=user_chat_id,
                audio=media_input,
                caption=caption_text,
            )
        # 8. DOCUMENT
        elif msg.message_type == "document":
            await bot.send_document(
                chat_id=user_chat_id,
                document=media_input,
                caption=caption_text,
            )
        # 9. STICKER
        elif msg.message_type == "sticker":
            await bot.send_sticker(
                chat_id=user_chat_id,
                sticker=media_input,
            )
        # 10. OTHER FALLBACK
        else:
            full_text = f"{header}\n{caption_body}".strip()
            await bot.send_message(
                chat_id=user_chat_id,
                text=full_text,
            )
    except Exception as exc:
        logger.warning(
            "API LIMITATION: Could not send media file, sending View-Once notice",
            msg_id=msg.message_id,
            error=str(exc),
        )
        if is_view_once_candidate(msg):
            notice = format_view_once_notice(msg)
            await bot.send_message(
                chat_id=user_chat_id,
                text=notice,
            )
        else:
            raise


@router.deleted_business_messages()
async def on_deleted_business_messages(
    event: BusinessMessagesDeleted, bot: Bot
) -> None:
    """Handle deleted_business_messages update."""
    conn_id = event.business_connection_id
    chat_id = event.chat.id

    async with get_db_session() as session:
        from app.config import get_settings
        conn = await get_business_connection(session, conn_id)
        target_chat_id = conn.user_chat_id if conn else get_settings().admin_id

        found_msgs: list[MessageModel] = []
        for msg_id in event.message_ids:
            try:
                db_msg = await mark_message_deleted(session, conn_id, chat_id, msg_id)
                if db_msg:
                    found_msgs.append(db_msg)
                else:
                    logger.debug(
                        "Deleted message not found in cache",
                        conn_id=conn_id[:8] + "...",
                        chat_id=chat_id,
                        msg_id=msg_id,
                    )
            except Exception as exc:
                logger.error(
                    "Error marking message deleted",
                    conn_id=conn_id[:8] + "...",
                    msg_id=msg_id,
                    error=str(exc),
                )

        if not found_msgs:
            return

        from app.services.media_group import group_deleted_messages, send_restored_album

        singles, albums = group_deleted_messages(found_msgs)

        # 1. Send album media groups
        for _group_id, album_msgs in albums.items():
            first_msg = album_msgs[0]
            header = _format_header(first_msg)
            sent_ok = await send_restored_album(bot, target_chat_id, conn_id, album_msgs, header)
            if not sent_ok:
                # Fallback: if send_media_group fails, send as singles
                singles.extend(album_msgs)

        # 2. Send single messages
        for msg in singles:
            try:
                await send_restored_deleted_message(bot, target_chat_id, msg)
                logger.info(
                    "Restored deleted business message sent",
                    conn_id=conn_id[:8] + "...",
                    chat_id=chat_id,
                    msg_id=msg.message_id,
                    msg_type=msg.message_type,
                )
            except Exception as exc:
                logger.error(
                    "Failed to restore deleted message",
                    conn_id=conn_id[:8] + "...",
                    chat_id=chat_id,
                    msg_id=msg.message_id,
                    error=str(exc),
                )
