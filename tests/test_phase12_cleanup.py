"""Phase 12 tests — Automatic retention & cleanup policy logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connections import upsert_business_connection
from app.database.models import Base, MessageModel, MessageVersionModel
from app.services.cleanup import purge_expired_messages


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


class TestRetentionCleanup:
    @pytest.mark.asyncio
    async def test_purge_expired_messages_removes_old_data(
        self, async_session: AsyncSession
    ):
        await upsert_business_connection(
            async_session, "bc_1200", 123, 123, True
        )

        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=10)
        recent_date = now - timedelta(days=1)

        # 1. Add expired message (10 days old)
        old_msg = MessageModel(
            business_connection_id="bc_1200",
            chat_id=555,
            message_id=1,
            sender_id=123,
            date=old_date,
            created_at=old_date,
            message_type="text",
            category="TEXT",
            text="Old message",
        )
        async_session.add(old_msg)
        await async_session.flush()

        old_ver = MessageVersionModel(
            message_pk=old_msg.id,
            version_number=1,
            text="Old message",
            edited_at=old_date,
        )
        async_session.add(old_ver)

        # 2. Add recent message (1 day old)
        recent_msg = MessageModel(
            business_connection_id="bc_1200",
            chat_id=555,
            message_id=2,
            sender_id=123,
            date=recent_date,
            created_at=recent_date,
            message_type="text",
            category="TEXT",
            text="Recent message",
        )
        async_session.add(recent_msg)
        await async_session.commit()

        # Execute purge with 7 days TTL
        stats = await purge_expired_messages(async_session, ttl_days=7)

        assert stats["messages_deleted"] == 1

        # Verify old message is gone, recent message remains
        res = await async_session.execute(select(MessageModel))
        remaining = list(res.scalars().all())

        assert len(remaining) == 1
        assert remaining[0].message_id == 2
        assert remaining[0].text == "Recent message"
