"""Phase 1 — smoke tests: config loading and logging setup."""

from __future__ import annotations

import os

import pytest

from app.logging_setup import setup_logging


class TestConfigLoading:
    """Settings must load correctly from environment variables."""

    def _make_settings(self, **overrides):
        """Helper: patch env and return a fresh Settings instance."""
        from app.config import Settings

        env = {
            "BOT_TOKEN": "123456:ABC-DEF",
            "ADMIN_ID": "42",
            "POSTGRES_PASSWORD": "test_pg_pass",
            "REDIS_PASSWORD": "test_redis_pass",
            **overrides,
        }
        # Settings reads from env; patch os.environ temporarily
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            return Settings()  # type: ignore[call-arg]
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_valid_config_loads(self):
        s = self._make_settings()
        assert s.admin_id == 42
        assert s.bot_mode == "polling"
        assert s.message_cache_ttl_days == 7

    def test_bot_token_is_secret(self):
        s = self._make_settings()
        # SecretStr should not expose value via str()
        assert "123456" not in str(s.bot_token)

    def test_admin_id_must_be_positive(self):
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            self._make_settings(ADMIN_ID="-1")

    def test_async_database_url_constructed(self):
        s = self._make_settings(
            POSTGRES_HOST="db",
            POSTGRES_PORT="5432",
            POSTGRES_DB="mydb",
            POSTGRES_USER="usr",
            POSTGRES_PASSWORD="secret",
        )
        url = s.async_database_url
        assert url.startswith("postgresql+asyncpg://")
        assert "usr" in url
        assert "mydb" in url
        # SecretStr fields must NOT expose their raw value via str()
        assert "**********" in str(s.postgres_password)  # masked
        assert s.postgres_password.get_secret_value() == "secret"  # accessible when needed

    def test_redis_url_includes_password(self):
        s = self._make_settings(REDIS_PASSWORD="redispass")
        url = s.redis_url
        assert "redispass" in url  # it's in the connection string, that's expected
        assert url.startswith("redis://")

    def test_log_level_default(self):
        s = self._make_settings()
        assert s.log_level == "INFO"

    def test_cache_ttl_range(self):
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            self._make_settings(MESSAGE_CACHE_TTL_DAYS="0")  # below ge=1


class TestLoggingSetup:
    """Logging skeleton must not raise and must redact secrets."""

    def test_setup_does_not_raise(self):
        setup_logging(log_level="DEBUG", json_logs=False)

    def test_json_mode_does_not_raise(self):
        setup_logging(log_level="INFO", json_logs=True)

    def test_secret_redaction(self):
        from app.logging_setup import _redact_sensitive

        event = {
            "event": "startup",
            "bot_token": "secret_token_value",
            "password": "hunter2",
            "admin_id": 42,
        }
        result = _redact_sensitive(None, None, event)  # type: ignore[arg-type]
        assert result["bot_token"] == "***REDACTED***"
        assert result["password"] == "***REDACTED***"
        assert result["admin_id"] == 42  # non-sensitive field untouched
