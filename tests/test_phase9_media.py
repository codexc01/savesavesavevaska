"""Phase 9 tests — Media Group (Album) handling logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot

from app.database.models import MessageModel
from app.services.media_group import group_deleted_messages, send_restored_album


def _make_msg(
    msg_id: int, media_group_id: str | None = None, msg_type: str = "photo"
) -> MessageModel:
    return MessageModel(
        id=msg_id,
        business_connection_id="bc_900",
        chat_id=123,
        message_id=msg_id,
        sender_id=456,
        sender_name="Alice",
        date=datetime.now(timezone.utc),
        message_type=msg_type,
        category=msg_type.upper(),
        file_id=f"file_{msg_id}",
        media_group_id=media_group_id,
    )


class TestMediaGrouping:
    def test_group_deleted_messages_separates_albums_from_singles(self):
        m1 = _make_msg(101, media_group_id="album_A", msg_type="photo")
        m2 = _make_msg(102, media_group_id="album_A", msg_type="photo")
        m3 = _make_msg(103, media_group_id=None, msg_type="text")

        singles, albums = group_deleted_messages([m1, m2, m3])

        assert len(singles) == 1
        assert singles[0].message_id == 103
        assert "album_A" in albums
        assert len(albums["album_A"]) == 2

    def test_single_album_message_treated_as_single(self):
        m1 = _make_msg(201, media_group_id="album_solo", msg_type="photo")

        singles, albums = group_deleted_messages([m1])

        assert len(singles) == 1
        assert len(albums) == 0


class TestSendRestoredAlbum:
    @pytest.mark.asyncio
    async def test_send_restored_album_calls_send_media_group(self):
        bot = AsyncMock(spec=Bot)
        m1 = _make_msg(301, media_group_id="alb_1", msg_type="photo")
        m2 = _make_msg(302, media_group_id="alb_1", msg_type="video")

        ok = await send_restored_album(
            bot=bot,
            user_chat_id=123,
            business_connection_id="bc_900",
            album_msgs=[m1, m2],
            header_text="Restored Album Header",
        )

        assert ok is True
        bot.send_media_group.assert_awaited_once()
        media_param = bot.send_media_group.call_args[1]["media"]
        assert len(media_param) == 2
