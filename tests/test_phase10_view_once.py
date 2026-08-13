"""Phase 10 tests — View-Once & Ephemeral media limitation protocol."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import Message

from app.database.models import MessageModel
from app.handlers.deleted import send_restored_deleted_message
from app.services.view_once import format_view_once_notice, is_view_once_candidate


def _make_db_msg_view_once() -> MessageModel:
    return MessageModel(
        id=1,
        business_connection_id="bc_1000",
        chat_id=888,
        message_id=5001,
        sender_id=999,
        sender_name="Dave",
        sender_username="dave_test",
        date=datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc),
        message_type="photo",
        category="PHOTO",
        file_id="expired_view_once_file_id",
        is_deleted=False,
        raw_metadata={"has_protected_content": True},
    )


class TestViewOnceDetection:
    def test_is_view_once_candidate_aiogram_msg(self):
        msg = MagicMock(spec=Message)
        msg.has_protected_content = True
        msg.has_media_spoiler = False
        assert is_view_once_candidate(msg) is True

    def test_is_view_once_candidate_db_msg(self):
        db_msg = _make_db_msg_view_once()
        assert is_view_once_candidate(db_msg) is True

    def test_format_view_once_notice_text(self):
        db_msg = _make_db_msg_view_once()
        notice = format_view_once_notice(db_msg)
        assert "Исчезающее медиа (View-Once)" in notice
        assert "Dave" in notice
        assert "Telegram API защищает данный контент" in notice


class TestViewOnceFallbackHandler:
    @pytest.mark.asyncio
    async def test_view_once_fallback_sends_notice_when_send_photo_fails(self):
        bot = AsyncMock(spec=Bot)
        bot.send_photo.side_effect = Exception(
            "Telegram API error: file_id expired / protected content"
        )

        db_msg = _make_db_msg_view_once()

        await send_restored_deleted_message(bot, 888, db_msg)

        # send_photo failed, so send_message was called with the View-Once limitation notice
        bot.send_photo.assert_awaited_once()
        bot.send_message.assert_awaited_once()

        sent_text = bot.send_message.call_args[1]["text"]
        assert "Исчезающее медиа (View-Once)" in sent_text
