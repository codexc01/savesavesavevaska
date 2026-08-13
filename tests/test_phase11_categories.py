"""Phase 11 tests — Domain content categories & taxonomy."""

from __future__ import annotations

from unittest.mock import MagicMock

from aiogram.types import Chat, Message, PhotoSize, Sticker, VideoNote, Voice

from app.domain.categories import ContentCategory
from app.services.archive import extract_message_metadata


def _make_msg() -> MagicMock:
    chat = MagicMock(spec=Chat)
    chat.id = 111

    msg = MagicMock(spec=Message)
    msg.business_connection_id = "bc_1100"
    msg.chat = chat
    msg.message_id = 999
    msg.from_user = None
    msg.date = None
    msg.text = None
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
    return msg


class TestContentCategoryClassification:
    def test_classify_text(self):
        msg = _make_msg()
        msg.text = "Hello world"

        cat = ContentCategory.classify_message(msg)
        assert cat == ContentCategory.TEXT

    def test_classify_photo(self):
        msg = _make_msg()
        msg.photo = [MagicMock(spec=PhotoSize)]

        cat = ContentCategory.classify_message(msg)
        assert cat == ContentCategory.PHOTO

    def test_classify_voice(self):
        msg = _make_msg()
        msg.voice = MagicMock(spec=Voice)

        cat = ContentCategory.classify_message(msg)
        assert cat == ContentCategory.VOICE

    def test_classify_video_note(self):
        msg = _make_msg()
        msg.video_note = MagicMock(spec=VideoNote)

        cat = ContentCategory.classify_message(msg)
        assert cat == ContentCategory.VIDEO_NOTE

    def test_classify_sticker(self):
        msg = _make_msg()
        msg.sticker = MagicMock(spec=Sticker)

        cat = ContentCategory.classify_message(msg)
        assert cat == ContentCategory.STICKER

    def test_classify_media_group(self):
        msg = _make_msg()
        msg.media_group_id = "album_12345"
        msg.photo = [MagicMock(spec=PhotoSize)]

        cat = ContentCategory.classify_message(msg)
        assert cat == ContentCategory.MEDIA_GROUP


class TestArchiveMetadataCategory:
    def test_metadata_extraction_uses_content_category(self):
        msg = _make_msg()
        photo = MagicMock(spec=PhotoSize)
        photo.file_id = "f1"
        photo.file_unique_id = "u1"
        msg.photo = [photo]
        msg.media_group_id = "album_99"

        meta = extract_message_metadata(msg)
        assert meta["category"] == ContentCategory.MEDIA_GROUP.value
