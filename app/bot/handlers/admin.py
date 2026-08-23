"""Admin commands: /special, /stats and /broadcast."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot import texts
from app.services import admins as admin_service
from app.services import video as video_service
from app.store.json_store import Store
from app.store.models import User

logger = logging.getLogger(__name__)
router = Router(name="admin")

ADMIN_COMMANDS = [
    ("/special", "shu ro'yxat"),
    ("/kanallar", "majburiy kanallar ro'yxati"),
    ("/kanal_qoshish @kanal", "majburiy kanal qo'shish"),
    ("/kanal_ochirish @kanal", "majburiy kanalni o'chirish"),
    ("/kanal_tozalash", "barcha majburiy kanallarni o'chirish"),
    ("/adminlar", "adminlar ro'yxati"),
    ("/admin_qoshish ID", "yangi admin qo'shish"),
    ("/admin_ochirish ID", "adminlikdan olish"),
    ("/video", "videoni o'rnatish (javob sifatida yoki havola bilan)"),
    ("/video_ochirish", "videoni o'chirish"),
    ("/stats", "statistika"),
    ("/broadcast matn", "barcha foydalanuvchilarga xabar yuborish"),
]


@router.message(Command("special"))
async def cmd_special(message: Message, user: User) -> None:
    """One place that lists every admin-only command."""
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    rows = "\n".join(
        texts.SPECIAL_ROW.format(command=command, description=description)
        for command, description in ADMIN_COMMANDS
    )
    await message.answer(texts.SPECIAL_HEADER + rows)


@router.message(Command("stats"))
async def cmd_stats(message: Message, store: Store, user: User) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    users, tests, attempts = store.stats()
    await message.answer(texts.ADMIN_STATS.format(users=users, tests=tests, attempts=attempts))


def _replied_video_file_id(message: Message) -> str | None:
    """file_id of the video being replied to, if there is one.

    Covers both shapes people send in: an ordinary video and a video attached
    as a file. Animations (GIFs) are not videos to Telegram, so they are
    rejected rather than stored as something send_video cannot play.
    """
    replied = message.reply_to_message
    if replied is None:
        return None
    if replied.video is not None:
        return replied.video.file_id
    document = replied.document
    if document is not None and (document.mime_type or "").startswith("video/"):
        return document.file_id
    return None


@router.message(Command("video"))
async def set_help_video(
    message: Message, command: CommandObject, store: Store, user: User
) -> None:
    """Point the intro button at a video: reply with /video, or pass a link."""
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    args = (command.args or "").strip()

    if args.lower().startswith(("http://", "https://")):
        await video_service.set_url(store, args)
        await message.answer(texts.VIDEO_URL_SAVED.format(button=texts.BTN_HELP_VIDEO))
        return

    if args:
        await message.answer(texts.VIDEO_USAGE)
        return

    file_id = _replied_video_file_id(message)
    if file_id is None:
        await message.answer(texts.VIDEO_USAGE)
        return

    await video_service.set_file_id(store, file_id)
    await message.answer(texts.VIDEO_SAVED.format(button=texts.BTN_HELP_VIDEO))


@router.message(Command("video_ochirish"))
async def clear_help_video(message: Message, store: Store, user: User) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    await video_service.clear(store)
    await message.answer(texts.VIDEO_REMOVED)


@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: Message, command: CommandObject, store: Store, user: User
) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    body = (command.args or "").strip()
    if not body:
        await message.answer(texts.BROADCAST_USAGE)
        return

    recipients = [record.id for record in store.all_users() if not record.is_blocked]

    sent = 0
    failed = 0
    for index, chat_id in enumerate(recipients):
        try:
            await message.bot.send_message(chat_id, body)
            sent += 1
        except Exception:
            failed += 1
        # Telegram tolerates roughly 30 messages a second to distinct chats.
        if index % 25 == 24:
            await asyncio.sleep(1)

    await message.answer(texts.BROADCAST_DONE.format(sent=sent, failed=failed))


@router.message(Command("id"))
async def cmd_my_id(message: Message, user: User) -> None:
    """Anyone can look up their own id — that is how you become an admin."""
    await message.answer(texts.MY_ID.format(user_id=user.id))


@router.message(Command("adminlar"))
async def list_admins(message: Message, store: Store, user: User) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    ids = admin_service.current_ids(store)
    rows = []
    for index, admin_id in enumerate(ids, start=1):
        record = store.get_user(admin_id)
        name = f" — {record.full_name}" if record and record.full_name else ""
        rows.append(
            texts.ADMIN_ROW.format(
                index=index,
                user_id=admin_id,
                name=name,
                origin=texts.ADMIN_ORIGINS[admin_service.origin(store, admin_id)],
            )
        )

    await message.answer(
        texts.ADMINS_HEADER.format(count=len(ids)) + "\n".join(rows) + texts.ADMINS_USAGE
    )


def _target_id(message: Message, args: str) -> int | None:
    """The user id being acted on: an explicit argument, or a forwarded message."""
    args = (args or "").strip()
    if args:
        cleaned = args.lstrip("@").strip()
        return int(cleaned) if cleaned.isdigit() else None

    replied = message.reply_to_message
    if replied is not None and replied.forward_from is not None:
        return replied.forward_from.id
    return None


@router.message(Command("admin_qoshish"))
async def add_admin(
    message: Message, command: CommandObject, store: Store, user: User
) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    args = (command.args or "").strip()
    replied = message.reply_to_message

    if not args and replied is not None and replied.forward_from is None:
        # Forwarded, but the original sender is hidden by their privacy setting.
        await message.answer(texts.ADMIN_FORWARD_HIDDEN)
        return

    target = _target_id(message, args)
    if target is None:
        await message.answer(texts.ADMIN_BAD_ID.format(value=args) if args else texts.ADMIN_ADD_USAGE)
        return

    ids, added = await admin_service.add(store, target)
    if not added:
        await message.answer(texts.ADMIN_ALREADY.format(user_id=target))
        return

    # Keep the stored flag in step so the new admin does not have to wait for
    # their next message before the middleware notices.
    record = store.get_user(target)
    if record is not None and not record.is_admin:
        record.is_admin = True
        await store.save_user(record)

    await message.answer(texts.ADMIN_ADDED.format(user_id=target, count=len(ids)))

    try:
        await message.bot.send_message(target, texts.ADMIN_NOTIFIED)
    except Exception:
        logger.info("Could not notify %s about becoming an admin", target)


@router.message(Command("admin_ochirish"))
async def remove_admin(
    message: Message, command: CommandObject, store: Store, user: User
) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    args = (command.args or "").strip()
    if not args:
        await message.answer(texts.ADMIN_REMOVE_USAGE)
        return

    target = _target_id(message, args)
    if target is None:
        await message.answer(texts.ADMIN_BAD_ID.format(value=args))
        return

    source = admin_service.origin(store, target)
    if source == "owner":
        await message.answer(texts.ADMIN_CANNOT_REMOVE_OWNER)
        return
    if source == "env":
        await message.answer(texts.ADMIN_CANNOT_REMOVE_ENV.format(user_id=target))
        return

    ids, removed = await admin_service.remove(store, target)
    if not removed:
        await message.answer(texts.ADMIN_NOT_FOUND.format(user_id=target))
        return

    record = store.get_user(target)
    if record is not None and record.is_admin:
        record.is_admin = False
        await store.save_user(record)

    await message.answer(texts.ADMIN_REMOVED.format(user_id=target, count=len(ids)))
