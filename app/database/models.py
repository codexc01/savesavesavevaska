"""SQLAlchemy 2.x Async Models for SaveMOD Telegram Business Bot.

Entities:
  - BusinessConnectionModel: tracks active & historic Telegram Business Account connections
  - MessageModel: temporary & historic cache of incoming business messages
  - MessageVersionModel: history of edits for each message (v1, v2, v3...)
  - MediaMetadataModel: details of media attached to messages (file_id, size, category, etc.)
  - ProcessedUpdateModel: idempotency tracker for Telegram update_ids
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSONB().with_variant(JSON, "sqlite")
BigIntType = BigInteger().with_variant(Integer, "sqlite")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class BusinessConnectionModel(Base):
    """Tracks connected Telegram Business Accounts."""

    __tablename__ = "business_connections"

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    business_connection_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rights: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    # Relationships
    messages: Mapped[list[MessageModel]] = relationship(
        "MessageModel", back_populates="connection", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_bus_conn_user_status", "user_id", "is_enabled"),)


class MessageModel(Base):
    """Stores incoming business messages for delete & edit tracking."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    business_connection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("business_connections.business_connection_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    sender_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sender_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(
        String(32), default="TEXT", nullable=False, index=True
    )

    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_unique_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    local_file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    media_group_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )

    reply_to_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    raw_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    # Relationships
    connection: Mapped[BusinessConnectionModel] = relationship(
        "BusinessConnectionModel", back_populates="messages"
    )
    versions: Mapped[list[MessageVersionModel]] = relationship(
        "MessageVersionModel",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageVersionModel.version_number",
    )
    media_item: Mapped[Optional[MediaMetadataModel]] = relationship(
        "MediaMetadataModel",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "business_connection_id",
            "chat_id",
            "message_id",
            name="uq_msg_conn_chat_msg_id",
        ),
        Index("idx_msg_lookup", "business_connection_id", "chat_id", "message_id"),
        Index("idx_msg_created_ttl", "created_at", "is_deleted"),
    )


class MessageVersionModel(Base):
    """Tracks full version history of edited messages."""

    __tablename__ = "message_versions"

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    message_pk: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    message: Mapped[MessageModel] = relationship(
        "MessageModel", back_populates="versions"
    )

    __table_args__ = (
        UniqueConstraint(
            "message_pk", "version_number", name="uq_msg_version_number"
        ),
    )


class MediaMetadataModel(Base):
    """Stores detailed metadata for media attached to business messages."""

    __tablename__ = "media_metadata"

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    message_pk: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_unique_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    has_spoiler: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_view_once: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    message: Mapped[MessageModel] = relationship(
        "MessageModel", back_populates="media_item"
    )


class ProcessedUpdateModel(Base):
    """Idempotency guard — logs processed update IDs."""

    __tablename__ = "processed_updates"

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    update_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    update_type: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )


class BannedUserModel(Base):
    """Tracks users banned by admin from using the bot."""

    __tablename__ = "banned_users"

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    banned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
