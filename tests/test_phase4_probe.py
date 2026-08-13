"""Phase 4 tests — Business API Probe logic."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.types import BusinessMessagesDeleted, Chat, Message, User

from app.diagnostics.business_probe import (
    _build_report,
    _mark,
    _safe_msg_info,
    cmd_probe_report,
    get_probe_results,
    probe_business_message,
    probe_deleted_messages,
    probe_edited_message,
)


def _make_msg(text: str = "hello", conn_id: str = "conn_123456789") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 111
    chat = MagicMock(spec=Chat)
    chat.id = 222

    msg = MagicMock(spec=Message)
    msg.message_id = 100
    msg.business_connection_id = conn_id
    msg.from_user = user
    msg.chat = chat
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


class TestProbeCore:
    def test_safe_msg_info_redacts_connection_id(self):
        msg = _make_msg(conn_id="abcdef123456")
        info = _safe_msg_info(msg)
        assert info["message_id"] == 100
        assert info["business_connection_id"] == "abcdef12..."

    def test_mark_and_get_results(self):
        _mark("text_message", "✅ SUPPORTED", "Test note")
        res = get_probe_results()
        assert res["text_message"]["status"] == "✅ SUPPORTED"
        assert res["text_message"]["notes"] == "Test note"

    def test_build_report(self):
        report = _build_report()
        assert "Business API Probe Report" in report
        assert "business_connection" in report


class TestProbeHandlers:
    @pytest.mark.asyncio
    async def test_probe_business_message_when_enabled(self):
        msg = _make_msg(text="probe test message")
        bot = AsyncMock(spec=Bot)

        with patch("app.diagnostics.business_probe.is_probe_enabled", return_value=True):
            await probe_business_message(msg, bot)

        res = get_probe_results()
        assert res["text_message"]["status"] == "✅ SUPPORTED"

    @pytest.mark.asyncio
    async def test_probe_edited_message(self):
        msg = _make_msg(text="edited message")
        with patch("app.diagnostics.business_probe.is_probe_enabled", return_value=True):
            await probe_edited_message(msg)

        res = get_probe_results()
        assert res["edited_business_message"]["status"] == "✅ SUPPORTED"

    @pytest.mark.asyncio
    async def test_probe_deleted_messages(self):
        chat = MagicMock(spec=Chat)
        chat.id = 222
        event = MagicMock(spec=BusinessMessagesDeleted)
        event.business_connection_id = "conn_123456"
        event.chat = chat
        event.message_ids = [101, 102]

        with patch("app.diagnostics.business_probe.is_probe_enabled", return_value=True):
            await probe_deleted_messages(event)

        res = get_probe_results()
        assert res["deleted_business_messages"]["status"] == "✅ SUPPORTED"

    @pytest.mark.asyncio
    async def test_cmd_probe_report_admin_access(self):
        msg = _make_msg()
        msg.from_user.id = 2106121176  # ADMIN_ID in test settings default

        env = {"BOT_TOKEN": "123:ABC", "ADMIN_ID": "2106121176"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch("app.diagnostics.business_probe.is_probe_enabled", return_value=True),
        ):
            await cmd_probe_report(msg)

        msg.answer.assert_called_once()
