"""Admin Panel & Interactive Inline UI — Phase 13 / Ultra-Optimised.

SECURITY & PRIVACY RULES:
  1. Access strictly restricted to ADMIN_ID from config.
  2. Non-admin users MUST NOT see any admin commands or callback buttons.
  3. Non-admin access attempts produce SILENT DENIAL (no response sent).

OPTIMISATION:
  - Low RAM/Disk overhead via strict query limit/offset pagination.
  - Zero message clutter: updates UI in-place via edit_text on inline callbacks.
"""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select

from app.config import get_settings
from app.database.connections import get_business_connection, list_business_connections
from app.database.models import MessageModel
from app.database.session import get_db_session
from app.diagnostics.business_probe import get_probe_results

logger = structlog.get_logger(__name__)
router = Router(name="admin")


class AdminGuardFilter(BaseFilter):
    """Filter enforcing strict ADMIN_ID restriction for messages & callbacks."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if not user:
            return False
        admin_id = get_settings().admin_id
        if user.id != admin_id:
            logger.warning(
                "Unauthorised admin access attempt silently denied",
                user_id=user.id,
            )
            return False
        return True


# Apply AdminGuardFilter to both messages and callback queries in this router
router.message.filter(AdminGuardFilter())
router.callback_query.filter(AdminGuardFilter())


def _build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build sleek main dashboard inline keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="👥 Бизнес-аккаунты", callback_data="adm:conns:0"),
            InlineKeyboardButton(text="💬 Все чаты", callback_data="adm:chats:0"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:menu"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _render_main_dashboard() -> tuple[str, InlineKeyboardMarkup]:
    """Render main dashboard status text and inline keyboard."""
    settings = get_settings()
    async with get_db_session() as session:
        all_conns = await list_business_connections(session, active_only=True)
        active_conns = [c for c in all_conns if c.is_enabled]

        # Count total stored messages
        msg_count_stmt = select(func.count(MessageModel.id))
        total_msgs = (await session.execute(msg_count_stmt)).scalar() or 0

    text = (
        "<b>⚙️ Админ-панель управления</b>\n\n"
        "<b>Статус:</b> 🟢 Онлайн\n"
        f"<b>Режим:</b> <code>{settings.bot_mode}</code>\n"
        f"<b>Подключений:</b> {len(active_conns)} активных\n"
        f"<b>Сохранено сообщений:</b> {total_msgs}\n"
        f"<b>TTL кэша:</b> {settings.message_cache_ttl_days} дн.\n\n"
        "<i>Используйте кнопки меню ниже или команды /connections, /chats</i>"
    )
    return text, _build_main_menu_keyboard()


@router.message(Command("admin"))
async def cmd_admin(msg: Message) -> None:
    """Entry point command /admin."""
    text, reply_markup = await _render_main_dashboard()
    await msg.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data == "adm:menu")
async def cb_admin_menu(cb: CallbackQuery) -> None:
    """Callback for returning to main admin menu."""
    text, reply_markup = await _render_main_dashboard()
    if cb.message:
        await cb.message.edit_text(text, reply_markup=reply_markup)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:conns:"))
async def cb_list_connections(cb: CallbackQuery) -> None:
    """List all connected business accounts with pagination."""
    page = int(cb.data.split(":")[2])
    limit = 5
    offset = page * limit

    async with get_db_session() as session:
        all_conns = await list_business_connections(session, active_only=True)

    total = len(all_conns)
    page_conns = all_conns[offset : offset + limit]

    if not all_conns:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="adm:menu")]]
        )
        if cb.message:
            await cb.message.edit_text(
                "📋 <i>Нет зарегистрированных бизнес-подключений</i>",
                reply_markup=kb,
            )
        await cb.answer()
        return

    text_lines = [f"<b>👥 Подключённые бизнес-аккаунты ({total}):</b>\n"]
    buttons = []

    for c in page_conns:
        status_icon = "🟢" if c.is_enabled else "🔴"
        user_info = f"@{c.username}" if c.username else f"ID {c.user_id}"
        text_lines.append(f"{status_icon} <b>{user_info}</b> (ID: <code>{c.user_id}</code>)")

        # Button per account
        conn_cb = f"adm:conn:{c.business_connection_id}"
        buttons.append([InlineKeyboardButton(text=f"👤 {user_info}", callback_data=conn_cb)])

    # Pagination buttons
    nav_btns = []
    if page > 0:
        nav_btns.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm:conns:{page - 1}")
        )
    if offset + limit < total:
        nav_btns.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"adm:conns:{page + 1}")
        )

    if nav_btns:
        buttons.append(nav_btns)

    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="adm:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if cb.message:
        await cb.message.edit_text("\n".join(text_lines), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:conn:"))
async def cb_account_detail(cb: CallbackQuery) -> None:
    """Show detailed menu for a selected business connection."""
    conn_id = cb.data.split(":")[2]

    async with get_db_session() as session:
        conn = await get_business_connection(session, conn_id)

        # Count stored messages for this connection
        stmt = select(func.count(MessageModel.id)).where(
            MessageModel.business_connection_id == conn_id
        )
        count = (await session.execute(stmt)).scalar() or 0

    if not conn:
        await cb.answer("Подключение не найдено", show_alert=True)
        return

    status = "🟢 Активно" if conn.is_enabled else "🔴 Отключено"
    user_info = f"@{conn.username}" if conn.username else f"ID {conn.user_id}"

    text = (
        f"<b>👤 Бизнес-аккаунт:</b> {user_info}\n"
        f"<b>Статус:</b> {status}\n"
        f"<b>User ID:</b> <code>{conn.user_id}</code>\n"
        f"<b>Conn ID:</b> <code>{conn.business_connection_id[:12]}...</code>\n"
        f"<b>Сохранено сообщений:</b> {count}\n"
    )

    buttons = [
        [
            InlineKeyboardButton(
                text="💬 Чаты этого аккаунта",
                callback_data=f"adm:cchats:{conn_id}:0",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Удалить и заблокировать",
                callback_data=f"adm:ban:{conn_id}",
            )
        ],
        [InlineKeyboardButton(text="🔙 К списку аккаунтов", callback_data="adm:conns:0")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if cb.message:
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ban:"))
async def cb_ban_prompt(cb: CallbackQuery) -> None:
    """Prompt confirmation before banning a user."""
    conn_id = cb.data.split(":")[2]

    async with get_db_session() as session:
        conn = await get_business_connection(session, conn_id)

    if not conn:
        await cb.answer("Подключение не найдено", show_alert=True)
        return

    user_info = f"@{conn.username}" if conn.username else f"ID {conn.user_id}"

    text = (
        "<b>⚠️ Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите <b>удалить и заблокировать</b> пользователя "
        f"<b>{user_info}</b> (ID: <code>{conn.user_id}</code>)?\n\n"
        "<i>Все его сохранённые данные и подключение будут безвозвратно удалены.</i>"
    )

    buttons = [
        [
            InlineKeyboardButton(
                text="⛔ Да, удалить и заблокировать",
                callback_data=f"adm:banconf:{conn_id}",
            )
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"adm:conn:{conn_id}")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if cb.message:
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:banconf:"))
async def cb_ban_confirm(cb: CallbackQuery) -> None:
    """Execute ban and purge user data."""
    conn_id = cb.data.split(":")[2]

    from app.database.connections import ban_and_remove_user

    async with get_db_session() as session:
        conn = await get_business_connection(session, conn_id)
        if not conn:
            await cb.answer("Пользователь уже удалён", show_alert=True)
            return

        user_id = conn.user_id
        username = conn.username

        await ban_and_remove_user(session, user_id, username)

    await cb.answer("❌ Пользователь успешно удалён и заблокирован!", show_alert=True)
    await cb_list_connections(cb)


@router.callback_query(F.data.startswith("adm:cchats:"))
async def cb_conn_chats(cb: CallbackQuery) -> None:
    """List active business chats for a specific business connection."""
    parts = cb.data.split(":")
    conn_id = parts[2]
    page = int(parts[3])
    limit = 5
    offset = page * limit

    async with get_db_session() as session:
        conn = await get_business_connection(session, conn_id)
        if conn and conn.username:
            owner_name = f"@{conn.username}"
        elif conn:
            owner_name = f"ID {conn.user_id}"
        else:
            owner_name = ""

        # Group chats for this conn_id
        stmt = (
            select(
                MessageModel.chat_id,
                MessageModel.sender_name,
                MessageModel.sender_username,
            )
            .where(MessageModel.business_connection_id == conn_id)
            .group_by(
                MessageModel.chat_id,
                MessageModel.sender_name,
                MessageModel.sender_username,
            )
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        chats = res.all()

        # Count total chats
        count_stmt = (
            select(func.count(func.distinct(MessageModel.chat_id)))
            .where(MessageModel.business_connection_id == conn_id)
        )
        total_chats = (await session.execute(count_stmt)).scalar() or 0

    if not chats:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm:conn:{conn_id}")]
            ]
        )
        if cb.message:
            await cb.message.edit_text(
                f"💬 <i>У аккаунта {owner_name} пока нет сохранённых чатов</i>",
                reply_markup=kb,
            )
        await cb.answer()
        return

    text_lines = [
        f"<b>💬 Чаты пользователя {owner_name} (всего: {total_chats}):</b>\n",
        "<i>Нажмите на кнопку с именем собеседника, чтобы открыть его сообщения:</i>\n",
    ]
    buttons = []

    for chat_id, sender_name, username in chats:
        name = sender_name or (f"@{username}" if username else f"Чат {chat_id}")
        user_info = f"{name} (@{username})" if username else name
        btn_cb = f"adm:msgs:{conn_id}:{chat_id}:0"
        buttons.append([InlineKeyboardButton(text=f"👤 {user_info}", callback_data=btn_cb)])

    nav_btns = []
    if page > 0:
        nav_btns.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm:cchats:{conn_id}:{page - 1}")
        )
    if offset + limit < total_chats:
        nav_btns.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"adm:cchats:{conn_id}:{page + 1}")
        )

    if nav_btns:
        buttons.append(nav_btns)

    buttons.append(
        [InlineKeyboardButton(text="🔙 К аккаунту", callback_data=f"adm:conn:{conn_id}")]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if cb.message:
        await cb.message.edit_text("\n".join(text_lines), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:chats:"))
async def cb_all_chats(cb: CallbackQuery) -> None:
    """List all stored business chats across all connections."""
    page = int(cb.data.split(":")[2])
    limit = 5
    offset = page * limit

    async with get_db_session() as session:
        stmt = (
            select(
                MessageModel.chat_id,
                MessageModel.business_connection_id,
                MessageModel.sender_name,
                MessageModel.sender_username,
            )
            .group_by(
                MessageModel.chat_id,
                MessageModel.business_connection_id,
                MessageModel.sender_name,
                MessageModel.sender_username,
            )
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        chats = res.all()

        count_stmt = select(func.count(func.distinct(MessageModel.chat_id)))
        total_chats = (await session.execute(count_stmt)).scalar() or 0

    if not chats:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="adm:menu")]]
        )
        if cb.message:
            await cb.message.edit_text("💬 <i>Сохранённых чатов пока нет</i>", reply_markup=kb)
        await cb.answer()
        return

    text_lines = [
        f"<b>💬 Все сохранённые чаты ({total_chats}):</b>\n",
        "<i>Нажмите на собеседника для просмотра переписки:</i>\n",
    ]
    buttons = []

    for chat_id, conn_id, sender_name, username in chats:
        name = sender_name or (f"@{username}" if username else f"Чат {chat_id}")
        user_info = f"{name} (@{username})" if username else name
        btn_cb = f"adm:msgs:{conn_id}:{chat_id}:0"
        buttons.append([InlineKeyboardButton(text=f"👤 {user_info}", callback_data=btn_cb)])

    nav_btns = []
    if page > 0:
        nav_btns.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm:chats:{page - 1}")
        )
    if offset + limit < total_chats:
        nav_btns.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"adm:chats:{page + 1}")
        )

    if nav_btns:
        buttons.append(nav_btns)

    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="adm:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if cb.message:
        await cb.message.edit_text("\n".join(text_lines), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:msgs:"))
async def cb_chat_messages(cb: CallbackQuery) -> None:
    """View saved messages for a selected chat with pagination."""
    parts = cb.data.split(":")
    conn_id = parts[2]
    chat_id = int(parts[3])
    page = int(parts[4])
    limit = 5
    offset = page * limit

    async with get_db_session() as session:
        stmt = (
            select(MessageModel)
            .where(
                MessageModel.business_connection_id == conn_id,
                MessageModel.chat_id == chat_id,
            )
            .order_by(MessageModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        msgs = list(res.scalars().all())

        count_stmt = select(func.count(MessageModel.id)).where(
            MessageModel.business_connection_id == conn_id,
            MessageModel.chat_id == chat_id,
        )
        total_msgs = (await session.execute(count_stmt)).scalar() or 0

    if not msgs:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm:cchats:{conn_id}:0")]
            ]
        )
        if cb.message:
            await cb.message.edit_text(
                "📜 <i>В этом чате нет сохранённых сообщений</i>",
                reply_markup=kb,
            )
        await cb.answer()
        return

    first_msg = msgs[0]
    chat_user_name = first_msg.sender_name or "Собеседник"
    if first_msg.sender_username:
        user_link = f'<a href="https://t.me/{first_msg.sender_username}">{chat_user_name}</a>'
    elif first_msg.sender_id:
        user_link = f'<a href="tg://user?id={first_msg.sender_id}">{chat_user_name}</a>'
    else:
        user_link = f"<b>{chat_user_name}</b>"

    text_lines = [
        f"<b>📜 Переписка с {user_link} (всего: {total_msgs}):</b>\n",
    ]

    type_labels = {
        "photo": "📷 Фото",
        "video": "🎥 Видео",
        "voice": "🎤 Голосовое",
        "video_note": "⭕️ Кружок",
        "animation": "🎞 GIF",
        "audio": "🎵 Аудио",
        "document": "📄 Документ",
        "sticker": "🎨 Стикер",
    }

    buttons = []
    # Display messages in natural chronological order (oldest -> newest)
    chronological_msgs = list(reversed(msgs))

    for m in chronological_msgs:
        status_tag = "🗑 <b>[УДАЛЕНО]</b> " if m.is_deleted else ""
        sender = m.sender_name or (f"@{m.sender_username}" if m.sender_username else "Собеседник")
        media_label = type_labels.get(m.message_type, "")

        content = (
            m.text
            or m.caption
            or (f"[{media_label}]" if media_label else f"[{m.message_type}]")
        )
        if len(content) > 120:
            content = content[:117] + "..."

        if media_label:
            text_lines.append(f"{status_tag}<b>{sender}</b> [{media_label}]: {content}")
            btn_title = f"{'🗑 ' if m.is_deleted else ''}{media_label} (от {sender})"
            cb_data = f"adm:msgview:{m.id}"
            buttons.append([InlineKeyboardButton(text=btn_title, callback_data=cb_data)])
        else:
            text_lines.append(f"{status_tag}<b>{sender}:</b> {content}")

    text_lines.append("\n<i>Нажмите на медиа-кнопку ниже для просмотра фото/видео/голосового:</i>")

    nav_btns = []
    if page > 0:
        nav_btns.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"adm:msgs:{conn_id}:{chat_id}:{page - 1}",
            )
        )
    if offset + limit < total_msgs:
        nav_btns.append(
            InlineKeyboardButton(
                text="Вперёд ▶️",
                callback_data=f"adm:msgs:{conn_id}:{chat_id}:{page + 1}",
            )
        )

    if nav_btns:
        buttons.append(nav_btns)

    buttons.append(
        [InlineKeyboardButton(text="🔙 К чатам аккаунта", callback_data=f"adm:cchats:{conn_id}:0")]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if cb.message:
        await cb.message.edit_text("\n".join(text_lines), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:msgview:"))
async def cb_view_single_message(cb: CallbackQuery) -> None:
    """Send stored media file or full detail text directly to admin."""
    from aiogram import Bot

    db_msg_id = int(cb.data.split(":")[2])
    bot: Bot = cb.bot  # type: ignore[assignment]

    async with get_db_session() as session:
        stmt = select(MessageModel).where(MessageModel.id == db_msg_id)
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

    if not msg:
        await cb.answer("Сообщение не найдено в базе", show_alert=True)
        return

    sender = msg.sender_name or (f"@{msg.sender_username}" if msg.sender_username else "Собеседник")
    status_label = "🗑 [УДАЛЁННОЕ]" if msg.is_deleted else "💬 [СОХРАНЁННОЕ]"
    header = f"<b>{status_label} {msg.message_type.upper()}</b> от <b>{sender}</b>"

    caption_body = msg.caption or msg.text or ""
    caption_text = f"{header}\n{caption_body}".strip()

    file_id = msg.file_id
    admin_id = get_settings().admin_id

    import os

    from aiogram.types import FSInputFile

    if msg.local_file_path and os.path.exists(msg.local_file_path):
        media_input: str | FSInputFile = FSInputFile(msg.local_file_path)
    else:
        media_input = file_id  # type: ignore[assignment]

    try:
        if msg.message_type == "photo" and media_input:
            await bot.send_photo(chat_id=admin_id, photo=media_input, caption=caption_text)
        elif msg.message_type == "video" and media_input:
            await bot.send_video(chat_id=admin_id, video=media_input, caption=caption_text)
        elif msg.message_type == "voice" and media_input:
            await bot.send_voice(chat_id=admin_id, voice=media_input, caption=caption_text)
        elif msg.message_type == "video_note" and media_input:
            await bot.send_message(chat_id=admin_id, text=header)
            await bot.send_video_note(chat_id=admin_id, video_note=media_input)
        elif msg.message_type == "animation" and media_input:
            await bot.send_animation(chat_id=admin_id, animation=media_input, caption=caption_text)
        elif msg.message_type == "audio" and media_input:
            await bot.send_audio(chat_id=admin_id, audio=media_input, caption=caption_text)
        elif msg.message_type == "document" and media_input:
            await bot.send_document(chat_id=admin_id, document=media_input, caption=caption_text)
        elif msg.message_type == "sticker" and media_input:
            await bot.send_message(chat_id=admin_id, text=header)
            await bot.send_sticker(chat_id=admin_id, sticker=media_input)
        else:
            full_text = f"{header}\n\n{caption_body}"
            await bot.send_message(chat_id=admin_id, text=full_text)

        await cb.answer("Медиафайл отправлен вам в чат! 📥")
    except Exception as exc:
        logger.warning("Could not send admin media preview", error=str(exc))
        full_text = f"{header}\n\n{caption_body}\n\n⚠️ <i>(Медиа недоступно в API)</i>"
        await bot.send_message(chat_id=admin_id, text=full_text)
        await cb.answer("Информация отправлена в чат")


@router.message(Command("stats"))
@router.callback_query(F.data == "adm:stats")
async def cmd_stats(event: Message | CallbackQuery) -> None:
    """Show Business Probe & runtime stats."""
    probe_data = get_probe_results()
    supported_count = sum(1 for v in probe_data.values() if v.get("status") == "✅ SUPPORTED")

    lines = [
        "<b>📊 Системная статистика API</b>\n",
        f"Проверено возможностей API: {len(probe_data)}",
        f"Подтверждено (SUPPORTED): {supported_count}",
    ]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В главное меню", callback_data="adm:menu")]]
    )
    if isinstance(event, CallbackQuery):
        if event.message:
            await event.message.edit_text("\n".join(lines), reply_markup=kb)
        await event.answer()
    else:
        await event.answer("\n".join(lines), reply_markup=kb)


@router.message(Command("connections"))
async def cmd_connections(msg: Message) -> None:
    """Show detailed list of connected business accounts."""
    async with get_db_session() as session:
        all_conns = await list_business_connections(session)

    if not all_conns:
        await msg.answer("📋 <i>Нет зарегистрированных бизнес-подключений</i>")
        return

    lines = [f"<b>📋 Список подключений ({len(all_conns)}):</b>\n"]
    for idx, c in enumerate(all_conns, 1):
        status = "🟢 Активно" if c.is_enabled else "🔴 Отключено"
        user_info = f"@{c.username}" if c.username else f"ID {c.user_id}"
        lines.append(f"{idx}. <b>{user_info}</b> — {status}")

    await msg.answer("\n".join(lines))


@router.message(Command("chats"))
async def cmd_chats(msg: Message) -> None:
    """Show active business chats with saved messages."""
    page = 0
    limit = 5
    offset = page * limit

    async with get_db_session() as session:
        stmt = (
            select(
                MessageModel.chat_id,
                MessageModel.business_connection_id,
                MessageModel.sender_name,
                MessageModel.sender_username,
            )
            .group_by(
                MessageModel.chat_id,
                MessageModel.business_connection_id,
                MessageModel.sender_name,
                MessageModel.sender_username,
            )
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        chats = res.all()

        count_stmt = select(func.count(func.distinct(MessageModel.chat_id)))
        total_chats = (await session.execute(count_stmt)).scalar() or 0

    if not chats:
        await msg.answer("💬 <i>Сохранённых чатов пока нет</i>")
        return

    text_lines = [f"<b>💬 Все сохранённые бизнес-чаты ({total_chats}):</b>\n"]
    buttons = []

    for chat_id, conn_id, sender_name, username in chats:
        name = sender_name or (f"@{username}" if username else f"Чат {chat_id}")
        text_lines.append(f"• <b>{name}</b> (<code>ID: {chat_id}</code>)")
        btn_cb = f"adm:msgs:{conn_id}:{chat_id}:0"
        buttons.append([InlineKeyboardButton(text=f"💬 {name}", callback_data=btn_cb)])

    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="adm:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await msg.answer("\n".join(text_lines), reply_markup=kb)
