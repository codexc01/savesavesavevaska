"""Phase 7 tests — Deleted Business Messages restoration logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import BusinessMessagesDeleted, Chat
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connections import upsert_business_connection
from app.database.messages import save_message
from app.database.models import Base, MessageModel
from app.handlers.deleted import (
    _format_header,
    on_deleted_business_messages,
    send_restored_deleted_message,
)


@pytest.fixture
async def async_session() -> AsyncSession:
    """In-memory SQLite session fixture."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _make_db_msg(
    msg_type: str = "text",
    text: str | None = "Deleted hello",
    caption: str | None = None,
    file_id: str | None = None,
) -> MessageModel:
    msg = MessageModel(
        id=1,
        business_connection_id="bc_700",
        chat_id=888,
        message_id=2001,
        sender_id=999,
        sender_name="Bob",
        sender_username="bob_test",
        date=datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc),
        message_type=msg_type,
        category=msg_type.upper(),
        text=text,
        caption=caption,
        file_id=file_id,
        is_deleted=False,
    )
    return msg


class TestHeaderFormatting:
    def test_format_header_contains_sender_and_link(self):
        msg = _make_db_msg()
        header = _format_header(msg)
        assert "Удалённое сообщение" in header
        assert 'href="https://t.me/bob_test"' in header
        assert "Bob" in header


class TestRestorationSenders:
    @pytest.mark.asyncio
    async def test_send_text_message(self):
        bot = AsyncMock(spec=Bot)
        msg = _make_db_msg(msg_type="text", text="Original text")

        await send_restored_deleted_message(bot, 888, msg)
        bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_photo_message(self):
        bot = AsyncMock(spec=Bot)
        msg = _make_db_msg(msg_type="photo", file_id="ph_123", caption="Photo cap")

        await send_restored_deleted_message(bot, 888, msg)
        bot.send_photo.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_voice_message(self):
        bot = AsyncMock(spec=Bot)
        msg = _make_db_msg(msg_type="voice", file_id="vc_123")

        await send_restored_deleted_message(bot, 888, msg)
        bot.send_voice.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_video_note_message(self):
        bot = AsyncMock(spec=Bot)
        msg = _make_db_msg(msg_type="video_note", file_id="vn_123")

        await send_restored_deleted_message(bot, 888, msg)
        bot.send_video_note.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_sticker_message(self):
        bot = AsyncMock(spec=Bot)
        msg = _make_db_msg(msg_type="sticker", file_id="stk_123")

        await send_restored_deleted_message(bot, 888, msg)
        bot.send_sticker.assert_awaited_once()


class TestDeletedHandler:
    @pytest.mark.asyncio
    async def test_on_deleted_business_messages(self, async_session: AsyncSession):
        # Create connection & message in database
        await upsert_business_connection(
            async_session, "bc_700", 999, 888, True
        )
        dt = datetime.now(timezone.utc)
        await save_message(
            session=async_session,
            business_connection_id="bc_700",
            chat_id=888,
            message_id=2001,
            sender_id=999,
            date=dt,
            message_type="text",
            text="Text to be deleted",
        )

        chat = MagicMock(spec=Chat)
        chat.id = 888

        event = MagicMock(spec=BusinessMessagesDeleted)
        event.business_connection_id = "bc_700"
        event.chat = chat
        event.message_ids = [2001]

        bot = AsyncMock(spec=Bot)

        # Patch get_db_session to yield async_session
        from contextlib import asynccontextmanager
        from unittest.mock import patch

        @asynccontextmanager
        async def mock_db():
            yield async_session

        with patch("app.handlers.deleted.get_db_session", mock_db):
            await on_deleted_business_messages(event, bot)

        bot.send_message.assert_awaited_once()
