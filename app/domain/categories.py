"""Domain content categories & classification mapping — Phase 11.

Provides strongly-typed Enum ContentCategory for message classification,
used in PostgreSQL message indexing, search, filtering, and admin statistics.
"""

from __future__ import annotations

from enum import Enum

from aiogram.types import Message


class ContentCategory(str, Enum):
    """Categorization enum for stored business messages."""

    TEXT = "TEXT"
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    VOICE = "VOICE"
    VIDEO_NOTE = "VIDEO_NOTE"
    ANIMATION = "ANIMATION"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    STICKER = "STICKER"
    MEDIA_GROUP = "MEDIA_GROUP"
    OTHER = "OTHER"

    @classmethod
    def classify_message(cls, msg: Message) -> ContentCategory:
        """Determine ContentCategory from an incoming aiogram Message."""
        if getattr(msg, "media_group_id", None):
            return cls.MEDIA_GROUP
        if getattr(msg, "photo", None):
            return cls.PHOTO
        if getattr(msg, "video", None):
            return cls.VIDEO
        if getattr(msg, "voice", None):
            return cls.VOICE
        if getattr(msg, "video_note", None):
            return cls.VIDEO_NOTE
        if getattr(msg, "animation", None):
            return cls.ANIMATION
        if getattr(msg, "audio", None):
            return cls.AUDIO
        if getattr(msg, "document", None):
            return cls.DOCUMENT
        if getattr(msg, "sticker", None):
            return cls.STICKER
        if getattr(msg, "text", None):
            return cls.TEXT

        return cls.OTHER
