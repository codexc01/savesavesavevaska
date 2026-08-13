"""Phase 3 tests — Business Connection handling."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import BusinessBotRights, BusinessConnection, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id: int = 111, username: str = "testuser") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.username = username
    u.first_name = "Test"
    u.model_fields = {}
    return u


def _make_rights(**kwargs: bool) -> MagicMock:
    """Create a mock BusinessBotRights with specified fields."""
    rights = MagicMock(spec=BusinessBotRights)
    default_fields = {
        "can_reply": True,
        "can_read_messages": True,
        "can_delete_sent_messages": False,
        "can_delete_all_messages": False,
        "can_edit_name": False,
        "can_edit_bio": False,
        "can_edit_profile_photo": False,
        "can_edit_username": False,
        "can_change_gift_settings": False,
        "can_view_gifts_and_stars": False,
        "can_convert_gifts_to_stars": False,
        "can_transfer_and_upgrade_gifts": False,
        "can_transfer_stars": False,
        "can_manage_stories": False,
        "can_delete_outgoing_messages": False,
    }
    default_fields.update(kwargs)
    rights.model_fields = {k: None for k in default_fields}
    for k, v in default_fields.items():
        setattr(rights, k, v)
    return rights


def _make_conn(
    conn_id: str = "conn_abc123",
    user_id: int = 111,
    username: str = "testuser",
    is_enabled: bool = True,
    with_rights: bool = True,
) -> MagicMock:
    conn = MagicMock(spec=BusinessConnection)
    conn.id = conn_id
    conn.user = _make_user(user_id, username)
    conn.user_chat_id = user_id
    conn.is_enabled = is_enabled
    conn.rights = _make_rights() if with_rights else None
    conn.date = int(datetime.now(timezone.utc).timestamp())
    return conn


# ---------------------------------------------------------------------------
# _extract_rights
# ---------------------------------------------------------------------------

class TestExtractRights:
    def test_extracts_all_fields(self):
        from app.handlers.business import _extract_rights
        conn = _make_conn()
        rights = _extract_rights(conn)
        assert isinstance(rights, dict)
        assert "can_reply" in rights
        assert rights["can_reply"] is True

    def test_returns_empty_when_no_rights(self):
        from app.handlers.business import _extract_rights
        conn = _make_conn(with_rights=False)
        rights = _extract_rights(conn)
        assert rights == {}


# ---------------------------------------------------------------------------
# _upsert_connection
# ---------------------------------------------------------------------------

class TestUpsertConnection:
    def setup_method(self) -> None:
        """Clear in-memory store before each test."""
        import app.handlers.business as biz
        biz._connections.clear()

    def test_new_connection_is_created(self):
        from app.handlers.business import _upsert_connection
        conn = _make_conn(conn_id="new_001")
        record, created = _upsert_connection(conn)
        assert created is True
        assert record["business_connection_id"] == "new_001"
        assert record["is_enabled"] is True
        assert record["user_id"] == 111

    def test_duplicate_update_does_not_create_new(self):
        from app.handlers.business import _connections, _upsert_connection
        conn = _make_conn(conn_id="dup_001")
        _, c1 = _upsert_connection(conn)
        _, c2 = _upsert_connection(conn)  # same data
        assert c1 is True
        assert c2 is False
        assert len(_connections) == 1

    def test_disconnect_sets_is_enabled_false(self):
        from app.handlers.business import _upsert_connection
        conn = _make_conn(conn_id="disc_001", is_enabled=True)
        _upsert_connection(conn)

        conn_off = _make_conn(conn_id="disc_001", is_enabled=False)
        record, created = _upsert_connection(conn_off)
        assert created is False
        assert record["is_enabled"] is False

    def test_different_connections_stored_separately(self):
        from app.handlers.business import _connections, _upsert_connection
        _upsert_connection(_make_conn(conn_id="c1", user_id=1))
        _upsert_connection(_make_conn(conn_id="c2", user_id=2))
        assert len(_connections) == 2

    def test_username_update_detected(self):
        from app.handlers.business import _upsert_connection
        conn1 = _make_conn(conn_id="upd_001", username="old_name")
        _upsert_connection(conn1)

        conn2 = _make_conn(conn_id="upd_001", username="new_name")
        record, created = _upsert_connection(conn2)
        assert created is False
        assert record["username"] == "new_name"


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

class TestQueryFunctions:
    def setup_method(self) -> None:
        import app.handlers.business as biz
        biz._connections.clear()

    def test_get_connection_returns_correct(self):
        from app.handlers.business import _upsert_connection, get_connection
        _upsert_connection(_make_conn(conn_id="get_001"))
        res = get_connection("get_001")
        assert res is not None
        assert res["business_connection_id"] == "get_001"

    def test_get_connection_returns_none_for_unknown(self):
        from app.handlers.business import get_connection
        assert get_connection("unknown_id") is None

    def test_get_all_connections(self):
        from app.handlers.business import _upsert_connection, get_all_connections
        _upsert_connection(_make_conn(conn_id="a1", user_id=1))
        _upsert_connection(_make_conn(conn_id="a2", user_id=2))
        all_conn = get_all_connections()
        assert len(all_conn) == 2


# ---------------------------------------------------------------------------
# Handler: on_business_connection
# ---------------------------------------------------------------------------

class TestOnBusinessConnection:
    def setup_method(self) -> None:
        import app.handlers.business as biz
        biz._connections.clear()

    @pytest.mark.asyncio
    async def test_connection_event_stored(self):
        from app.handlers.business import _connections, on_business_connection

        mock_bot = AsyncMock(spec=Bot)
        mock_bot.send_message = AsyncMock()

        conn = _make_conn(conn_id="h_001", is_enabled=True)
        await on_business_connection(conn, mock_bot)

        assert "h_001" in _connections
        assert _connections["h_001"]["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_disconnect_event_stored(self):
        from app.handlers.business import _connections, on_business_connection

        mock_bot = AsyncMock(spec=Bot)
        mock_bot.send_message = AsyncMock()

        await on_business_connection(_make_conn(conn_id="h_002", is_enabled=True), mock_bot)
        await on_business_connection(_make_conn(conn_id="h_002", is_enabled=False), mock_bot)

        assert _connections["h_002"]["is_enabled"] is False
        assert _connections["h_002"]["disconnected_at"] is not None

    @pytest.mark.asyncio
    async def test_admin_notified_on_connect(self):
        from app.handlers.business import on_business_connection

        mock_bot = AsyncMock(spec=Bot)
        mock_bot.send_message = AsyncMock()

        await on_business_connection(_make_conn(conn_id="h_003", is_enabled=True), mock_bot)

        assert mock_bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_admin_notified_on_disconnect(self):
        from app.handlers.business import on_business_connection

        mock_bot = AsyncMock(spec=Bot)
        mock_bot.send_message = AsyncMock()

        await on_business_connection(_make_conn(conn_id="h_004", is_enabled=False), mock_bot)

        mock_bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_failure_does_not_raise(self):
        """Admin notification error must be swallowed — not crash the handler."""
        from app.handlers.business import on_business_connection

        mock_bot = AsyncMock(spec=Bot)
        mock_bot.send_message = AsyncMock(side_effect=Exception("network error"))

        # Should NOT raise even when send_message fails
        await on_business_connection(_make_conn(conn_id="h_005"), mock_bot)
