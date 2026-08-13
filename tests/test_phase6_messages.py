"""Phase 6 tests — Incoming Business Message caching & archiving."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, PhotoSize, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connections import upsert_business_connection
from app.database.models import Base
from app.handlers.messages import on_business_message
from app.services.archive import archive_business_message, extract_message_metadata


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


def _make_msg(
    text: str | None = "hello",
    conn_id: str = "bc_600",
    msg_id: int = 1001,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 555
    user.first_name = "Alice"
    user.username = "alice_test"

    chat = MagicMock(spec=Chat)
    chat.id = 777

    msg = MagicMock(spec=Message)
    msg.message_id = msg_id
    msg.business_connection_id = conn_id
    msg.from_user = user
    msg.chat = chat
    msg.date = datetime.now(timezone.utc)
    msg.text = text
    msg.caption = None
    msg.photo = None
    msg.video = None
    msg.voice = None
    msg.video_note = None
    msg.animation = None
    msg.audio = None
    msg.document = None
    msg.sticker = None
    msg.media_group_id = None
    msg.reply_to_message = None
    msg.has_media_spoiler = None
    msg.has_protected_content = None
    msg.answer = AsyncMock()
    return msg


class TestMetadataExtraction:
    def test_extract_text_metadata(self):
        msg = _make_msg(text="Test message")
        meta = extract_message_metadata(msg)

        assert meta["business_connection_id"] == "bc_600"
        assert meta["chat_id"] == 777
        assert meta["message_id"] == 1001
        assert meta["sender_id"] == 555
        assert meta["message_type"] == "text"
        assert meta["category"] == "TEXT"
        assert meta["text"] == "Test message"

    def test_extract_photo_metadata(self):
        msg = _make_msg(text=None)
        photo = MagicMock(spec=PhotoSize)
        photo.file_id = "ph_id_123"
        photo.file_unique_id = "ph_uniq_123"
        msg.photo = [photo]
        msg.caption = "Nice view"

        meta = extract_message_metadata(msg)
        assert meta["message_type"] == "photo"
        assert meta["category"] == "PHOTO"
        assert meta["file_id"] == "ph_id_123"
        assert meta["caption"] == "Nice view"


class TestArchiveService:
    @pytest.mark.asyncio
    async def test_archive_message_creates_record(self, async_session: AsyncSession):
        # Create connection first
        await upsert_business_connection(
            async_session, "bc_600", 555, 555, True
        )

        msg = _make_msg(text="Archived text")
        db_msg, created = await archive_business_message(async_session, msg)

        assert created is True
        assert db_msg is not None
        assert db_msg.text == "Archived text"

        # Verify no response was sent back to Telegram
        msg.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_archive_duplicate_message_returns_existing(
        self, async_session: AsyncSession
    ):
        await upsert_business_connection(
            async_session, "bc_600", 555, 555, True
        )

        msg = _make_msg(text="Dup test", msg_id=2002)
        _, c1 = await archive_business_message(async_session, msg)
        _, c2 = await archive_business_message(async_session, msg)

        assert c1 is True
        assert c2 is False


class TestMessageHandler:
    @pytest.mark.asyncio
    async def test_handler_ignores_msg_without_business_conn_id(self):
        msg = _make_msg(text="Public message")
        msg.business_connection_id = None
        bot = AsyncMock()

        await on_business_message(msg, bot)
        msg.answer.assert_not_called()
