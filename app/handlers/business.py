"""Business Connection handler — Phase 3.

Receives BusinessConnection updates when a user connects or disconnects
the bot from their Telegram Business account.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from aiogram import Bot, Router
from aiogram.types import BusinessConnection

from app.config import get_settings

logger = structlog.get_logger(__name__)
router = Router(name="business")

_settings = get_settings()

_connections: dict[str, dict] = {}


def _extract_rights(conn: BusinessConnection) -> dict:
    """Extract BusinessBotRights into a plain dict. Returns {} if no rights."""
    if conn.rights is None:
        return {}
    return {
        field: getattr(conn.rights, field, None)
        for field in conn.rights.model_fields
    }


def _upsert_connection(conn: BusinessConnection) -> tuple[dict, bool]:
    """Insert or update connection in memory store."""
    now = datetime.now(timezone.utc).isoformat()
    existing = _connections.get(conn.id)
    rights = _extract_rights(conn)

    if conn.is_enabled:
        # Purge any old stale connections for the same user_id with different connection_id
        to_delete = [
            cid for cid, r in _connections.items()
            if r.get("user_id") == conn.user.id and cid != conn.id
        ]
        for cid in to_delete:
            _connections.pop(cid, None)

    if existing is None:
        record = {
            "business_connection_id": conn.id,
            "user_id": conn.user.id,
            "username": conn.user.username,
            "first_name": conn.user.first_name,
            "user_chat_id": conn.user_chat_id,
            "is_enabled": conn.is_enabled,
            "rights": rights,
            "connected_at": now,
            "disconnected_at": None if conn.is_enabled else now,
            "updated_at": now,
        }
        _connections[conn.id] = record
        return record, True

    changed = (
        existing["is_enabled"] != conn.is_enabled
        or existing["rights"] != rights
        or existing["username"] != conn.user.username
        or existing["first_name"] != conn.user.first_name
    )

    existing["is_enabled"] = conn.is_enabled
    existing["rights"] = rights
    existing["username"] = conn.user.username
    existing["first_name"] = conn.user.first_name
    existing["user_chat_id"] = conn.user_chat_id

    if not conn.is_enabled:
        existing["disconnected_at"] = now

    if changed:
        existing["updated_at"] = now

    return existing, False


def get_all_connections() -> list[dict]:
    """Return all stored connections."""
    return list(_connections.values())


def get_connection(business_connection_id: str) -> dict | None:
    """Return single connection by id."""
    return _connections.get(business_connection_id)


@router.business_connection()
async def on_business_connection(conn: BusinessConnection, bot: Bot) -> None:
    """Handle BusinessConnection update — connect and disconnect."""
    from app.database.connections import is_user_banned, upsert_business_connection
    from app.database.session import get_db_session

    try:
        async with get_db_session() as session:
            if await is_user_banned(session, conn.user.id):
                logger.warning("Banned user attempted business connection", user_id=conn.user.id)
                return

            await upsert_business_connection(
                session,
                business_connection_id=conn.id,
                user_id=conn.user.id,
                user_chat_id=conn.user_chat_id,
                is_enabled=conn.is_enabled,
                username=conn.user.username,
                rights=_extract_rights(conn),
            )
    except Exception as exc:
        logger.error("Failed to persist business connection in DB", error=str(exc))

    record, created = _upsert_connection(conn)

    log_ctx = {
        "conn_id": conn.id[:8] + "...",
        "user_id": conn.user.id,
        "username": conn.user.username,
        "is_enabled": conn.is_enabled,
        "created": created,
    }

    if conn.is_enabled:
        logger.info("Business connection established", **log_ctx)
        try:
            await _notify_user_connected(bot, conn)
        except Exception as exc:
            logger.warning("User notification failed (connect)", error=str(exc))
        try:
            await _notify_admin_connected(bot, conn, record)
        except Exception as exc:
            logger.warning("Admin notification failed (connect)", error=str(exc))
    else:
        logger.info("Business connection disabled", **log_ctx)
        try:
            await _notify_admin_disconnected(bot, conn)
        except Exception as exc:
            logger.warning("Admin notification failed (disconnect)", error=str(exc))


async def _notify_user_connected(bot: Bot, conn: BusinessConnection) -> None:
    """Send user a confirmation message when they connect the bot."""
    user_chat_id = conn.user_chat_id or conn.user.id
    text = (
        "✅ <b>Бот успешно подключён!</b>\n\n"
        "Теперь бот начнёт сохранять удалённые и изменённые сообщения в твоих чатах"
    )
    await bot.send_message(chat_id=user_chat_id, text=text)


async def _notify_admin_connected(
    bot: Bot, conn: BusinessConnection, record: dict
) -> None:
    """Send admin a notification about new business connection."""
    rights = record.get("rights", {})
    rights_lines = [
        f"  • {k}: {'✅' if v else '❌'}"
        for k, v in rights.items()
        if v is not None
    ]
    rights_text = "\n".join(rights_lines) if rights_lines else "  нет данных"

    user_display = f"@{conn.user.username}" if conn.user.username else conn.user.first_name

    text = (
        "🟢 <b>Новое подключение</b>\n\n"
        f"👤 {user_display} (<code>{conn.user.id}</code>)\n"
        f"🔗 ID: <code>{conn.id[:12]}...</code>\n\n"
        f"<b>Права:</b>\n{rights_text}"
    )

    await bot.send_message(chat_id=_settings.admin_id, text=text)


async def _notify_admin_disconnected(bot: Bot, conn: BusinessConnection) -> None:
    """Send admin a notification about disconnection."""
    user_display = f"@{conn.user.username}" if conn.user.username else conn.user.first_name

    text = (
        "🔴 <b>Отключение</b>\n\n"
        f"👤 {user_display} (<code>{conn.user.id}</code>)\n"
        f"🔗 ID: <code>{conn.id[:12]}...</code>"
    )

    await bot.send_message(chat_id=_settings.admin_id, text=text)
