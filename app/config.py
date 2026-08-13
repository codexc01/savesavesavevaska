"""Application configuration — loaded once at startup from environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------
    bot_token: SecretStr = Field(
        default=SecretStr("8946292647:AAEffEa70ybp3nwKzax12Gk-Ee1GMs0kpyw"),
        description="Telegram Bot API token",
    )
    admin_id: int = Field(
        default=2106121176, description="Telegram user_id of the admin"
    )
    webhook_url: str = Field(default="", description="HTTPS webhook URL (production)")
    webhook_secret: SecretStr = Field(
        default=SecretStr(""), description="Webhook secret token"
    )

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="savemod")
    postgres_user: str = Field(default="savemod")
    postgres_password: SecretStr = Field(default=SecretStr(""))

    # Optional override — if set, takes precedence over individual fields
    database_url: str = Field(default="")

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_password: SecretStr = Field(default=SecretStr(""))
    redis_db: int = Field(default=0)

    @property
    def redis_url(self) -> str:
        pwd = self.redis_password.get_secret_value()
        auth = f":{pwd}@" if pwd else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ------------------------------------------------------------------
    # Application behaviour
    # ------------------------------------------------------------------
    bot_mode: Literal["polling", "webhook"] = Field(default="polling")
    message_cache_ttl_days: int = Field(default=7, ge=1, le=365)
    probe_enabled: bool = Field(default=True, description="Enable Business API probe mode")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    log_json: bool = Field(default=False, description="Emit JSON log lines")

    # ------------------------------------------------------------------
    # Media / Storage
    # ------------------------------------------------------------------
    temp_media_dir: str = Field(default="/tmp/savemod_media")

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("admin_id", mode="before")
    @classmethod
    def admin_id_must_be_positive(cls, v: int) -> int:
        if int(v) <= 0:
            raise ValueError("ADMIN_ID must be a positive Telegram user_id")
        return int(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Called once, reused everywhere."""
    return Settings()  # type: ignore[call-arg]
