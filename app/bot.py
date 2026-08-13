"""SaveMOD Bot — entry point.

Supports two run modes (controlled by BOT_MODE env var):
  - polling  : long-polling, good for local development
  - webhook  : HTTPS webhook, required for production
"""

from __future__ import annotations

import asyncio
import logging
import sys

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from app.admin import admin_router
from app.config import Settings, get_settings
from app.diagnostics.business_probe import router as probe_router
from app.handlers.base import router as base_router
from app.handlers.business import router as business_router
from app.handlers.deleted import router as deleted_router
from app.handlers.edited import router as edited_router
from app.handlers.messages import router as messages_router
from app.logging_setup import setup_logging

logger = structlog.get_logger(__name__)


async def _set_bot_commands(bot: Bot, admin_id: int) -> None:
    """Set bot commands with per-scope visibility.

    Regular users  → only /start in the menu.
    Admin          → /start + /admin + /connections + /status (visible only in admin's chat).
    """
    public_commands = [
        BotCommand(command="start", description="Инструкция бота"),
    ]
    admin_commands = [
        BotCommand(command="start", description="Инструкция бота"),
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="chats", description="Сохранённые чаты"),
        BotCommand(command="connections", description="Список подключений"),
        BotCommand(command="status", description="Системный статус"),
        BotCommand(command="probe_report", description="API Probe отчёт"),
    ]

    await bot.set_my_commands(public_commands, scope=BotCommandScopeAllPrivateChats())

    try:
        await bot.set_my_commands(
            admin_commands,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    except Exception as exc:
        logger.warning("Could not set admin command scope", error=str(exc))


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

async def _run_polling(bot: Bot, dp: Dispatcher) -> None:
    logger.info("Starting in polling mode")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def _run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    if not settings.webhook_url:
        logger.critical("BOT_MODE=webhook but WEBHOOK_URL is not set — aborting")
        sys.exit(1)

    webhook_path = "/webhook"
    full_url = settings.webhook_url.rstrip("/") + webhook_path

    await bot.set_webhook(
        url=full_url,
        secret_token=settings.webhook_secret.get_secret_value() or None,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    logger.info("Webhook set", url=full_url)

    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret.get_secret_value() or None,
    ).register(app, path=webhook_path)

    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()
    logger.info("Webhook server listening", host="0.0.0.0", port=8080)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_logs=settings.log_json)

    logger.info(
        "SaveMOD Bot initialising",
        mode=settings.bot_mode,
        admin_id=settings.admin_id,
    )

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(base_router)
    dp.include_router(admin_router)
    dp.include_router(business_router)
    dp.include_router(messages_router)
    dp.include_router(deleted_router)
    dp.include_router(edited_router)
    dp.include_router(probe_router)

    try:
        me = await bot.get_me()
        logger.info("Bot authenticated", username=me.username, bot_id=me.id)
    except Exception as exc:
        logger.critical("Failed to authenticate with Telegram", error=str(exc))
        await bot.session.close()
        sys.exit(1)

    await _set_bot_commands(bot, admin_id=settings.admin_id)

    from app.database.session import init_db_tables
    from app.workers.cleanup_worker import start_cleanup_loop

    try:
        await init_db_tables()
    except Exception as exc:
        logger.warning("Could not auto-verify DB tables on startup", error=str(exc))

    cleanup_task = asyncio.create_task(start_cleanup_loop())

    try:
        if settings.bot_mode == "webhook":
            await _run_webhook(bot, dp, settings)
        else:
            await _run_polling(bot, dp)
    finally:
        cleanup_task.cancel()
        await bot.session.close()
        logger.info("Shutting down")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interrupted by user")
        sys.exit(0)
