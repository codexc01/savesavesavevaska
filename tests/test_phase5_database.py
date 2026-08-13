"""Phase 5 tests — PostgreSQL / SQLAlchemy Async models & operations."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connections import (
    get_business_connection,
    list_business_connections,
    upsert_business_connection,
)
from app.database.edits import get_message_history, record_message_edit
from app.database.messages import get_message, mark_message_deleted, save_message
from app.database.models import Base


@pytest.fixture
async def async_session() -> AsyncSession:
    """Create an in-memory SQLite async engine & session for unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


class TestBusinessConnectionRepo:
    @pytest.mark.asyncio
    async def test_upsert_and_retrieve_connection(self, async_session: AsyncSession):
        conn, created = await upsert_business_connection(
            session=async_session,
            business_connection_id="bc_100",
            user_id=111,
            user_chat_id=111,
            is_enabled=True,
            rights={"can_reply": True},
            username="user100",
        )
        assert created is True
        assert conn.business_connection_id == "bc_100"

        # Repeat upsert (idempotence)
        conn_dup, created_dup = await upsert_business_connection(
            session=async_session,
            business_connection_id="bc_100",
            user_id=111,
            user_chat_id=111,
            is_enabled=True,
            rights={"can_reply": True},
            username="user100",
        )
        assert created_dup is False
        assert conn_dup.id == conn.id

        # Query single
        queried = await get_business_connection(async_session, "bc_100")
        assert queried is not None
        assert queried.username == "user100"

        # Query all
        all_conns = await list_business_connections(async_session)
        assert len(all_conns) == 1


class TestMessageRepo:
    @pytest.mark.asyncio
    async def test_save_and_retrieve_message(self, async_session: AsyncSession):
        # Create connection first
        await upsert_business_connection(
            async_session, "bc_200", 222, 222, True
        )

        dt = datetime.now(timezone.utc)
        msg, created = await save_message(
            session=async_session,
            business_connection_id="bc_200",
            chat_id=500,
            message_id=1,
            sender_id=222,
            date=dt,
            message_type="text",
            text="Hello world",
        )
        assert created is True
        assert msg.text == "Hello world"

        fetched = await get_message(async_session, "bc_200", 500, 1)
        assert fetched is not None
        assert len(fetched.versions) == 1
        assert fetched.versions[0].version_number == 1

        # Duplicate save returns existing
        dup_msg, dup_created = await save_message(
            session=async_session,
            business_connection_id="bc_200",
            chat_id=500,
            message_id=1,
            sender_id=222,
            date=dt,
            message_type="text",
            text="Hello world",
        )
        assert dup_created is False
        assert dup_msg.id == msg.id

        # Delete message
        deleted = await mark_message_deleted(async_session, "bc_200", 500, 1)
        assert deleted is not None
        assert deleted.is_deleted is True
        assert deleted.deleted_at is not None


class TestMessageEditsRepo:
    @pytest.mark.asyncio
    async def test_record_multiple_edits(self, async_session: AsyncSession):
        await upsert_business_connection(
            async_session, "bc_300", 333, 333, True
        )

        dt = datetime.now(timezone.utc)
        await save_message(
            session=async_session,
            business_connection_id="bc_300",
            chat_id=600,
            message_id=10,
            sender_id=333,
            date=dt,
            message_type="text",
            text="v1 text",
        )

        # Edit 1 -> v2
        msg, ver2 = await record_message_edit(
            async_session, "bc_300", 600, 10, new_text="v2 text"
        )
        assert ver2 is not None
        assert ver2.version_number == 2
        assert msg.text == "v2 text"

        # Edit duplicate -> ignored (returns None for new version)
        msg_dup, ver_dup = await record_message_edit(
            async_session, "bc_300", 600, 10, new_text="v2 text"
        )
        assert ver_dup is None

        # History list
        history = await get_message_history(async_session, "bc_300", 600, 10)
        assert len(history) == 2
        assert history[0].text == "v1 text"
        assert history[1].text == "v2 text"
