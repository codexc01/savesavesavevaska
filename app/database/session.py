"""PostgreSQL async database session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the global AsyncEngine instance with automatic SQLite fallback."""
    global _engine, _async_session_factory  # noqa: PLW0603

    if _engine is None:
        settings = get_settings()
        url = settings.async_database_url

        # Check if local postgres connection is reachable if url contains postgresql
        if "postgresql" in url:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            host = settings.postgres_host
            port = settings.postgres_port
            is_open = sock.connect_ex((host, port)) == 0
            sock.close()

            if not is_open:
                logger.warning(
                    "PostgreSQL host unavailable, falling back to local SQLite database",
                    host=host,
                    port=port,
                    sqlite_path="sqlite+aiosqlite:///./bot_data.sqlite3",
                )
                url = "sqlite+aiosqlite:///./bot_data.sqlite3"

        _engine = create_async_engine(
            url,
            echo=False,
        )
        _async_session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info("Database async engine initialized", url=url)

    return _engine


async def init_db_tables() -> None:
    """Create all metadata tables on active engine (called on bot startup)."""
    engine = get_engine()
    from app.database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Auto-migration for missing columns in existing SQLite/PG tables
        try:
            from sqlalchemy import text
            query = text("ALTER TABLE messages ADD COLUMN local_file_path VARCHAR(512);")
            await conn.execute(query)
        except Exception:
            pass  # Column already exists
    logger.info("Database schema tables auto-verified")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the global async_sessionmaker instance."""
    if _async_session_factory is None:
        get_engine()
    assert _async_session_factory is not None
    return _async_session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for acquiring an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db_engine() -> None:
    """Close the database engine connections pool."""
    global _engine, _async_session_factory  # noqa: PLW0603

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("PostgreSQL async engine disposed")
