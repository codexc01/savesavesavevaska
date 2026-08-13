"""Business API Probe — Phase 4.

Diagnostic module that captures real Telegram Business updates and
reports what the API actually provides.

Enable probe mode:
    PROBE_ENABLED=true  in .env

Admin commands:
    /probe_report  — show current feature table

Findings are stored in memory and also written to probe_results.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import BusinessMessagesDeleted, Message

from app.config import get_settings

logger = structlog.get_logger(__name__)
router = Router(name="probe")

_settings = get_settings()

def is_probe_enabled() -> bool:
    return get_settings().probe_enabled

RESULTS_FILE = Path(__file__).parent.parent.parent / "probe_results.json"

# ---------------------------------------------------------------------------
# Feature registry
# Each entry: feature_key → {status, notes, seen_at, raw_sample}
# Status: "✅ SUPPORTED" | "🟡 PARTIAL" | "❌ NOT AVAILABLE" | "⏳ NOT YET SEEN"
# ---------------------------------------------------------------------------
_FEATURE_KEYS = [
    "business_connection",
    "text_message",
    "photo_message",
    "video_message",
    "voice_message",
    "video_note_message",
    "animation_gif_message",
    "audio_message",
    "document_message",
    "sticker_message",
    "caption_on_media",
    "media_group_album",
    "reply_to_message",
    "edited_business_message",
    "deleted_business_messages",
    "has_media_spoiler_field",
    "has_protected_content_field",
    "view_once_photo",
    "view_once_video",
    "reply_to_view_once",
    "file_id_on_photo",
    "file_id_on_video",
    "file_id_on_voice",
    "file_id_on_video_note",
]

_results: dict[str, dict] = {
    key: {"status": "⏳ NOT YET SEEN", "notes": "", "seen_at": None, "sample": None}
    for key in _FEATURE_KEYS
}

# Mark business_connection as seen (Phase 3 confirmed it works)
_results["business_connection"] = {
    "status": "✅ SUPPORTED",
    "notes": "Confirmed in Phase 3 — connect/disconnect both received",
    "seen_at": datetime.now(timezone.utc).isoformat(),
    "sample": None,
}


def _mark(key: str, status: str, notes: str, sample: Any = None) -> None:
    """Record a probe result."""
    if key not in _results:
        logger.warning("Unknown probe key", key=key)
        return
    _results[key] = {
        "status": status,
        "notes": notes,
        "seen_at": datetime.now(timezone.utc).isoformat(),
        "sample": sample,
    }
    _save_results()
    logger.info("Probe result recorded", feature=key, status=status)


def _save_results() -> None:
    """Persist results to JSON file (no secrets stored)."""
    try:
        safe = {
            k: {kk: vv for kk, vv in v.items() if kk != "sample"}
            for k, v in _results.items()
        }
        RESULTS_FILE.write_text(json.dumps(safe, indent=2, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Could not save probe results", error=str(exc))


def _safe_msg_info(msg: Message) -> dict:
    """Extract safe (non-sensitive) metadata from a Message for logging."""
    return {
        "message_id": msg.message_id,
        "business_connection_id": msg.business_connection_id[:8] + "..."
        if msg.business_connection_id
        else None,
        "from_user_id": msg.from_user.id if msg.from_user else None,
        "chat_id": msg.chat.id if msg.chat else None,
        "has_text": bool(msg.text),
        "has_caption": bool(msg.caption),
        "has_photo": bool(msg.photo),
        "has_video": bool(msg.video),
        "has_voice": bool(msg.voice),
        "has_video_note": bool(msg.video_note),
        "has_animation": bool(msg.animation),
        "has_audio": bool(msg.audio),
        "has_document": bool(msg.document),
        "has_sticker": bool(msg.sticker),
        "media_group_id": msg.media_group_id,
        "has_reply": bool(msg.reply_to_message),
        "has_media_spoiler": msg.has_media_spoiler,
        "has_protected_content": msg.has_protected_content,
    }


# ---------------------------------------------------------------------------
# Business message probe handler
# ---------------------------------------------------------------------------

@router.business_message()
async def probe_business_message(msg: Message, bot: Bot) -> None:
    """Inspect every incoming business message and record its type."""
    if not is_probe_enabled():
        return

    info = _safe_msg_info(msg)
    logger.debug("PROBE: business_message received", **info)

    # --- Text ---
    if msg.text:
        _mark("text_message", "✅ SUPPORTED", f"text received, len={len(msg.text)}")

    # --- Photo ---
    if msg.photo:
        largest = msg.photo[-1]
        _mark(
            "photo_message",
            "✅ SUPPORTED",
            f"photo received, sizes={len(msg.photo)}, file_id present={bool(largest.file_id)}",
        )
        if largest.file_id:
            _mark("file_id_on_photo", "✅ SUPPORTED", f"file_id len={len(largest.file_id)}")

    # --- Video ---
    if msg.video:
        note_text = (
            f"video received, duration={msg.video.duration}s, "
            f"file_id present={bool(msg.video.file_id)}"
        )
        _mark("video_message", "✅ SUPPORTED", note_text)
        if msg.video.file_id:
            _mark("file_id_on_video", "✅ SUPPORTED", f"file_id len={len(msg.video.file_id)}")

    # --- Voice ---
    if msg.voice:
        note_text = (
            f"voice received, duration={msg.voice.duration}s, "
            f"file_id present={bool(msg.voice.file_id)}"
        )
        _mark("voice_message", "✅ SUPPORTED", note_text)
        if msg.voice.file_id:
            _mark("file_id_on_voice", "✅ SUPPORTED", f"file_id len={len(msg.voice.file_id)}")

    # --- Video Note (круглое) ---
    if msg.video_note:
        note_text = (
            f"video_note received, duration={msg.video_note.duration}s, "
            f"file_id present={bool(msg.video_note.file_id)}"
        )
        _mark("video_note_message", "✅ SUPPORTED", note_text)
        if msg.video_note.file_id:
            _mark(
                "file_id_on_video_note",
                "✅ SUPPORTED",
                f"file_id len={len(msg.video_note.file_id)}",
            )

    # --- Animation / GIF ---
    if msg.animation:
        _mark(
            "animation_gif_message",
            "✅ SUPPORTED",
            f"animation received, duration={msg.animation.duration}s",
        )

    # --- Audio ---
    if msg.audio:
        _mark(
            "audio_message",
            "✅ SUPPORTED",
            f"audio received, duration={msg.audio.duration}s",
        )

    # --- Document ---
    if msg.document:
        _mark(
            "document_message",
            "✅ SUPPORTED",
            f"document received, mime={msg.document.mime_type}",
        )

    # --- Sticker ---
    if msg.sticker:
        _mark(
            "sticker_message",
            "✅ SUPPORTED",
            f"sticker received, emoji={msg.sticker.emoji}, type={msg.sticker.type}",
        )

    # --- Caption ---
    if msg.caption and (msg.photo or msg.video or msg.animation or msg.audio or msg.document):
        _mark(
            "caption_on_media",
            "✅ SUPPORTED",
            f"caption present on media, len={len(msg.caption)}",
        )

    # --- Album ---
    if msg.media_group_id:
        _mark("media_group_album", "✅ SUPPORTED", f"media_group_id={msg.media_group_id}")

    # --- Reply ---
    if msg.reply_to_message:
        reply = msg.reply_to_message
        reply_info = {
            "reply_msg_id": reply.message_id,
            "reply_has_photo": bool(reply.photo),
            "reply_has_video": bool(reply.video),
            "reply_has_protected_content": reply.has_protected_content,
            "reply_has_media_spoiler": reply.has_media_spoiler,
        }
        _mark(
            "reply_to_message",
            "✅ SUPPORTED",
            f"reply received. original: {reply_info}",
            sample=reply_info,
        )

        # --- View Once detection ---
        # View-once media is media with has_protected_content or has_media_spoiler
        # We check what the reply message contains
        is_view_once_candidate = (
            reply.has_protected_content or reply.has_media_spoiler
        )

        if reply.photo and is_view_once_candidate:
            _mark(
                "view_once_photo",
                "🟡 PARTIAL",
                (
                    "Reply to photo with has_protected_content="
                    f"{reply.has_protected_content}, "
                    f"has_media_spoiler={reply.has_media_spoiler}. "
                    f"file_id present: {bool(reply.photo[-1].file_id if reply.photo else None)}"
                ),
                sample=reply_info,
            )
            _mark(
                "reply_to_view_once",
                "🟡 PARTIAL",
                "Reply to protected/spoiler photo detected",
            )

        if reply.video and is_view_once_candidate:
            _mark(
                "view_once_video",
                "🟡 PARTIAL",
                (
                    "Reply to video with has_protected_content="
                    f"{reply.has_protected_content}, "
                    f"has_media_spoiler={reply.has_media_spoiler}. "
                    f"file_id present: {bool(reply.video.file_id if reply.video else None)}"
                ),
                sample=reply_info,
            )
            _mark(
                "reply_to_view_once",
                "🟡 PARTIAL",
                "Reply to protected/spoiler video detected",
            )

    # --- has_media_spoiler ---
    if msg.has_media_spoiler is not None:
        _mark(
            "has_media_spoiler_field",
            "✅ SUPPORTED",
            f"has_media_spoiler field present = {msg.has_media_spoiler}",
        )

    # --- has_protected_content ---
    if msg.has_protected_content is not None:
        _mark(
            "has_protected_content_field",
            "✅ SUPPORTED",
            f"has_protected_content field present = {msg.has_protected_content}",
        )


# ---------------------------------------------------------------------------
# Edited message probe
# ---------------------------------------------------------------------------

@router.edited_business_message()
async def probe_edited_message(msg: Message) -> None:
    """Probe edited_business_message update."""
    if not is_probe_enabled():
        return

    info = _safe_msg_info(msg)
    logger.debug("PROBE: edited_business_message received", **info)

    _mark(
        "edited_business_message",
        "✅ SUPPORTED",
        f"edited message received: message_id={msg.message_id}, "
        f"has_text={bool(msg.text)}, has_caption={bool(msg.caption)}",
    )


# ---------------------------------------------------------------------------
# Deleted messages probe
# ---------------------------------------------------------------------------

@router.deleted_business_messages()
async def probe_deleted_messages(event: BusinessMessagesDeleted) -> None:
    """Probe deleted_business_messages update."""
    if not is_probe_enabled():
        return

    logger.debug(
        "PROBE: deleted_business_messages received",
        conn_id=event.business_connection_id[:8] + "...",
        chat_id=event.chat.id,
        message_ids=event.message_ids,
        count=len(event.message_ids),
    )

    _mark(
        "deleted_business_messages",
        "✅ SUPPORTED",
        f"deleted_business_messages received: count={len(event.message_ids)}, "
        f"fields=[business_connection_id, chat, message_ids]",
    )


# ---------------------------------------------------------------------------
# Admin command: /probe_report
# ---------------------------------------------------------------------------

def _build_report() -> str:
    """Build a human-readable probe report."""
    lines = ["<b>📊 Business API Probe Report</b>\n"]
    lines.append(f"<code>{'FEATURE':<35} {'STATUS':<20} NOTES</code>\n")

    for key, data in _results.items():
        status = data["status"]
        raw_notes = data.get("notes", "")
        notes = raw_notes[:60] + "..." if len(raw_notes) > 60 else raw_notes
        lines.append(f"<b>{key}</b>")
        lines.append(f"  {status}")
        if notes:
            lines.append(f"  {notes}")
        lines.append("")

    return "\n".join(lines)


@router.message(Command("probe_report"))
async def cmd_probe_report(msg: Message) -> None:
    """Admin-only: show probe results."""
    user = msg.from_user
    if not user or user.id != _settings.admin_id:
        return

    if not is_probe_enabled():
        await msg.answer(
            "⚠️ Probe mode is <b>disabled</b>\n\n"
            "Set <code>PROBE_ENABLED=true</code> in .env and restart the bot"
        )
        return

    report = _build_report()
    # Telegram message limit is 4096 chars — split if needed
    if len(report) > 4000:
        # Send as file
        await msg.answer("Отчёт слишком большой, отправлю файлом:")
        if RESULTS_FILE.exists():
            from aiogram.types import FSInputFile
            await msg.answer_document(
                FSInputFile(RESULTS_FILE, filename="probe_results.json")
            )
    else:
        await msg.answer(report)


def get_probe_results() -> dict:
    """Return current probe results (used by admin panel)."""
    return dict(_results)
