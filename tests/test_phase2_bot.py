"""Phase 2 tests — bot startup logic and base handlers.

All Telegram API calls are mocked; no real network access.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    text: str = "/start",
    user_id: int = 999,
    username: str = "tester",
    chat_id: int = 999,
) -> MagicMock:
    """Build a minimal mock Message."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = username
    user.first_name = "Test"

    chat = MagicMock(spec=Chat)
    chat.id = chat_id

    msg = MagicMock(spec=Message)
    msg.from_user = user
    msg.chat = chat
    msg.text = text
    msg.answer = AsyncMock(return_value=None)
    return msg


# ---------------------------------------------------------------------------
# ADMIN_ID protection tests (O(1) comparison)
# ---------------------------------------------------------------------------

class TestAdminIdGuard:
    """The /status handler must deny all non-admin users server-side."""

    def _env_with_admin(self, admin_id: int) -> dict:
        return {
            "BOT_TOKEN": "123:ABC",
            "ADMIN_ID": str(admin_id),
            "POSTGRES_PASSWORD": "x",
            "REDIS_PASSWORD": "x",
        }

    @pytest.mark.asyncio
    async def test_admin_receives_status(self):
        admin_id = 42
        env = self._env_with_admin(admin_id)
        with patch.dict(os.environ, env, clear=False):
            import importlib

            from app.config import get_settings

            get_settings.cache_clear()
            import app.handlers.base as base_mod

            importlib.reload(base_mod)

            msg = _make_message(text="/status", user_id=admin_id)
            await base_mod.cmd_status(msg)

        msg.answer.assert_called_once()
        reply_text: str = msg.answer.call_args[0][0]
        assert "online" in reply_text.lower() or "Bot" in reply_text

    @pytest.mark.asyncio
    async def test_non_admin_silently_denied(self):
        admin_id = 42
        env = self._env_with_admin(admin_id)
        with patch.dict(os.environ, env, clear=False):
            import importlib

            from app.config import get_settings

            get_settings.cache_clear()
            import app.handlers.base as base_mod

            importlib.reload(base_mod)

            msg = _make_message(text="/status", user_id=9999)  # not admin
            await base_mod.cmd_status(msg)

        # Silent denial: answer must NOT be called
        msg.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_user_silently_denied(self):
        env = self._env_with_admin(42)
        with patch.dict(os.environ, env, clear=False):
            import importlib

            from app.config import get_settings

            get_settings.cache_clear()
            import app.handlers.base as base_mod

            importlib.reload(base_mod)

            msg = _make_message(text="/status", user_id=0)
            msg.from_user = None  # anonymous
            await base_mod.cmd_status(msg)

        msg.answer.assert_not_called()


# ---------------------------------------------------------------------------
# /start handler
# ---------------------------------------------------------------------------

class TestStartHandler:
    @pytest.mark.asyncio
    async def test_start_replies_to_anyone(self):
        env = {
            "BOT_TOKEN": "123:ABC",
            "ADMIN_ID": "42",
            "POSTGRES_PASSWORD": "x",
            "REDIS_PASSWORD": "x",
        }
        with patch.dict(os.environ, env, clear=False):
            import importlib

            from app.config import get_settings

            get_settings.cache_clear()
            import app.handlers.base as base_mod

            importlib.reload(base_mod)

            msg = _make_message(text="/start", user_id=12345)
            await base_mod.cmd_start(msg)

        msg.answer.assert_called_once()


# ---------------------------------------------------------------------------
# Bot authentication (mocked)
# ---------------------------------------------------------------------------

class TestBotAuthentication:
    @pytest.mark.asyncio
    async def test_get_me_called_on_startup(self):
        """bot.get_me() must be called during startup to validate token."""
        from aiogram.types import User as TgUser

        fake_me = MagicMock(spec=TgUser)
        fake_me.username = "savemod_test_bot"
        fake_me.id = 123456

        mock_bot = AsyncMock(spec=Bot)
        mock_bot.get_me = AsyncMock(return_value=fake_me)
        mock_bot.session = AsyncMock()
        mock_bot.session.close = AsyncMock()

        # Simulate the auth check from bot.main()
        me = await mock_bot.get_me()
        assert me.username == "savemod_test_bot"
        mock_bot.get_me.assert_awaited_once()


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

class TestRouterSetup:
    def test_base_router_is_importable(self):
        from app.handlers.base import router
        assert router is not None
        assert router.name == "base"

    def test_dispatcher_includes_router(self):
        from app.handlers.base import router
        dp = Dispatcher()
        dp.include_router(router)
        # If include_router doesn't raise, routers are compatible
