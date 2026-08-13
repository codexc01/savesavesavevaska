"""Phase 13 tests — Admin Panel security & command handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.admin.panel import AdminGuardFilter, cmd_admin, cmd_connections, cmd_stats
from app.database.connections import upsert_business_connection
from app.database.models import Base


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


def _make_msg(user_id: int, text: str = "/admin") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id

    msg = MagicMock(spec=Message)
    msg.from_user = user
    msg.text = text
    msg.answer = AsyncMock()
    return msg


class TestAdminSecurityGuard:
    @pytest.mark.asyncio
    async def test_admin_guard_allows_admin(self):
        msg = _make_msg(user_id=2106121176)
        filter_obj = AdminGuardFilter()

        with patch("app.admin.panel.get_settings") as mock_settings:
            mock_settings.return_value.admin_id = 2106121176
            res = await filter_obj(msg)
            assert res is True

    @pytest.mark.asyncio
    async def test_admin_guard_denies_non_admin(self):
        msg = _make_msg(user_id=999999)  # Non admin ID
        filter_obj = AdminGuardFilter()

        with patch("app.admin.panel.get_settings") as mock_settings:
            mock_settings.return_value.admin_id = 2106121176
            res = await filter_obj(msg)
            assert res is False
            msg.answer.assert_called_once_with("⛔️ У вас нет прав доступа к админ-панели.")


class TestAdminCommands:
    @pytest.mark.asyncio
    async def test_cmd_admin_renders_dashboard(self, async_session: AsyncSession):
        msg = _make_msg(user_id=2106121176, text="/admin")

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db():
            yield async_session

        with patch("app.admin.panel.get_db_session", mock_db):
            await cmd_admin(msg)

        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "Админ-панель управления" in text
        assert "/connections" in text

    @pytest.mark.asyncio
    async def test_cmd_connections_lists_connections(self, async_session: AsyncSession):
        await upsert_business_connection(
            async_session, "bc_1300", 777, 777, True, username="admin_biz"
        )
        msg = _make_msg(user_id=2106121176, text="/connections")

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db():
            yield async_session

        with patch("app.admin.panel.get_db_session", mock_db):
            await cmd_connections(msg)

        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "Список подключений" in text
        assert "@admin_biz" in text

    @pytest.mark.asyncio
    async def test_cmd_stats_renders_stats(self):
        msg = _make_msg(user_id=2106121176, text="/stats")

        mock_probe = {"feature1": {"status": "✅ SUPPORTED"}}
        with patch("app.admin.panel.get_probe_results", return_value=mock_probe):
            await cmd_stats(msg)

        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "Системная статистика API" in text
