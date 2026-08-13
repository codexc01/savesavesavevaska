"""Phase 8 tests — Edited Business Messages tracking logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connections import upsert_business_connection
from app.database.messages import save_message
from app.database.models import Base, MessageModel, MessageVersionModel
from app.handlers.edited import _format_edit_notification, on_edited_business_message


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
    text: str = "New edited text", conn_id: str = "bc_800", msg_id: int = 3001
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 777
    user.first_name = "Charlie"
    user.username = "charlie_test"

    chat = MagicMock(spec=Chat)
    chat.id = 999

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
    msg.animation = None
    msg.document = None
    return msg


class TestEditNotificationFormatting:
    def test_format_edit_notification(self):
        msg = MessageModel(
            sender_name="Charlie",
            sender_username="charlie_test",
        )
        prev = MessageVersionModel(
            text="Original v1", edited_at=datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
        )
        curr = MessageVersionModel(
            text="Edited v2", edited_at=datetime(2026, 8, 14, 12, 5, tzinfo=timezone.utc)
        )

        res = _format_edit_notification(msg, prev, curr)
        assert "Изменённое сообщение" in res
        assert 'href="https://t.me/charlie_test"' in res
        assert "<b>Было:</b>\nOriginal v1" in res
        assert "<b>Стало:</b>\nEdited v2" in res


class TestEditedHandler:
    @pytest.mark.asyncio
    async def test_on_edited_business_message_sends_notification(
        self, async_session: AsyncSession
    ):
        await upsert_business_connection(
            async_session, "bc_800", 777, 999, True
        )
        dt = datetime.now(timezone.utc)
        await save_message(
            session=async_session,
            business_connection_id="bc_800",
            chat_id=999,
            message_id=3001,
            sender_id=777,
            date=dt,
            message_type="text",
            text="Old v1 text",
        )

        bot = AsyncMock(spec=Bot)
        msg = _make_msg(text="Updated v2 text")

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db():
            yield async_session

        with patch("app.handlers.edited.get_db_session", mock_db):
            await on_edited_business_message(msg, bot)

        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.call_args[1]["text"]
        assert "<b>Было:</b>\nOld v1 text" in sent_text
        assert "<b>Стало:</b>\nUpdated v2 text" in sent_text
