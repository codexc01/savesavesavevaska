"""Phase 15 tests — Full end-to-end integration flow suite."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.edits import get_message_history, record_message_edit
from app.database.messages import mark_message_deleted, save_message
from app.database.models import Base, MessageModel
from app.domain.categories import ContentCategory
from app.services.media_group import group_deleted_messages


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


class TestEndToEndLifecycle:
    @pytest.mark.asyncio
    async def test_full_message_lifecycle_archive_edit_delete(
        self, async_session: AsyncSession
    ):
        conn_id = "bc_integration_999"
        chat_id = 100200300
        msg_id = 77

        # Step 1: Incoming message received and archived
        now = datetime.now(timezone.utc)
        db_msg, created = await save_message(
            session=async_session,
            business_connection_id=conn_id,
            chat_id=chat_id,
            message_id=msg_id,
            sender_id=555,
            date=now,
            message_type="photo",
            category=ContentCategory.PHOTO.value,
            sender_name="Bob",
            caption="Initial caption v1",
            file_id="photo_file_123",
        )
        assert created is True
        assert db_msg.category == "PHOTO"

        # Step 2: Message edited in business chat (v1 -> v2)
        curr_msg, prev_ver = await record_message_edit(
            session=async_session,
            business_connection_id=conn_id,
            chat_id=chat_id,
            message_id=msg_id,
            new_text=None,
            new_caption="Edited caption v2",
        )

        assert curr_msg is not None
        assert curr_msg.caption == "Edited caption v2"

        # Check history versions saved
        history = await get_message_history(async_session, conn_id, chat_id, msg_id)
        assert len(history) >= 1

        # Step 4: Message deleted from chat
        deleted_msg = await mark_message_deleted(
            async_session, conn_id, chat_id, msg_id
        )
        assert deleted_msg is not None
        assert deleted_msg.is_deleted is True

        # Step 5: Check version history preservation
        history_after = await get_message_history(async_session, conn_id, chat_id, msg_id)
        assert len(history_after) >= 1

    @pytest.mark.asyncio
    async def test_album_media_group_aggregation_flow(self):
        m1 = MessageModel(
            id=1,
            business_connection_id="bc_alb",
            chat_id=1,
            message_id=10,
            sender_id=2,
            date=datetime.now(timezone.utc),
            message_type="photo",
            category="MEDIA_GROUP",
            media_group_id="group_x",
        )
        m2 = MessageModel(
            id=2,
            business_connection_id="bc_alb",
            chat_id=1,
            message_id=11,
            sender_id=2,
            date=datetime.now(timezone.utc),
            message_type="photo",
            category="MEDIA_GROUP",
            media_group_id="group_x",
        )

        singles, albums = group_deleted_messages([m1, m2])
        assert len(singles) == 0
        assert "group_x" in albums
        assert len(albums["group_x"]) == 2
