"""Admin commands for the required-channel gate.

The list may hold none, one, or many channels. Adding one is validated against
Telegram before it is stored, because the gate deliberately fails open: a
channel the bot cannot query is treated as joined, so an unvalidated entry
would look like a working restriction while letting everybody straight through.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import texts
from app.services import channels as channel_service
from app.store.json_store import Store
from app.store.models import User

logger = logging.getLogger(__name__)
router = Router(name="channels")


def _list_markup(channels: list[str]) -> InlineKeyboardMarkup | None:
    if not channels:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_REMOVE_CHANNEL.format(channel=channel),
                    callback_data=f"chan:rm:{channel}",
                )
            ]
            for channel in channels
        ]
    )


def _render(channels: list[str]) -> str:
    if not channels:
        return texts.CHANNELS_EMPTY + texts.CHANNELS_USAGE
    listing = "\n".join(f"{index}. {name}" for index, name in enumerate(channels, start=1))
    return texts.CHANNELS_HEADER.format(count=len(channels)) + "\n" + listing + texts.CHANNELS_USAGE


@router.message(Command("kanallar"))
async def list_channels(message: Message, store: Store, user: User) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return
    channels = channel_service.current(store)
    await message.answer(_render(channels), reply_markup=_list_markup(channels))


async def _verify(bot, channel: str) -> str | None:
    """Check the channel exists and the bot administers it.

    Returns an error message to show the admin, or None when it is usable.
    """
    try:
        chat = await bot.get_chat(channel)
    except Exception:
        logger.info("Cannot resolve channel %s", channel)
        return texts.CHANNEL_NOT_FOUND.format(channel=channel)

    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception:
        return texts.CHANNEL_BOT_NOT_ADMIN.format(channel=channel)

    if member.status not in ("administrator", "creator"):
        return texts.CHANNEL_BOT_NOT_ADMIN.format(channel=channel)
    return None


@router.message(Command("kanal_qoshish"))
async def add_channel(
    message: Message, command: CommandObject, store: Store, user: User
) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(texts.CHANNEL_ADD_USAGE)
        return

    try:
        candidate = channel_service.normalize(raw)
    except channel_service.ChannelError:
        await message.answer(texts.CHANNEL_BAD_FORMAT.format(value=raw))
        return

    if candidate.lower() in {item.lower() for item in channel_service.current(store)}:
        await message.answer(texts.CHANNEL_ALREADY.format(channel=candidate))
        return

    problem = await _verify(message.bot, candidate)
    if problem:
        await message.answer(problem)
        return

    channels, added = await channel_service.add(store, candidate)
    await message.answer(texts.CHANNEL_ADDED.format(channel=added, count=len(channels)))


@router.message(Command("kanal_ochirish"))
async def remove_channel(
    message: Message, command: CommandObject, store: Store, user: User
) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(texts.CHANNEL_REMOVE_USAGE)
        return

    channels, removed = await channel_service.remove(store, raw)
    if not removed:
        await message.answer(texts.CHANNEL_NOT_IN_LIST.format(channel=raw))
        return
    await message.answer(texts.CHANNEL_REMOVED.format(channel=raw, count=len(channels)))


@router.message(Command("kanal_tozalash"))
async def clear_channels(message: Message, store: Store, user: User) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return
    await channel_service.clear(store)
    await message.answer(texts.CHANNELS_CLEARED)


@router.callback_query(F.data.startswith("chan:rm:"))
async def remove_via_button(query: CallbackQuery, store: Store, user: User) -> None:
    if not user.is_admin:
        await query.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    channel = (query.data or "").split(":", 2)[2]
    channels, removed = await channel_service.remove(store, channel)
    await query.answer()

    if query.message:
        if removed:
            await query.message.answer(
                texts.CHANNEL_REMOVED.format(channel=channel, count=len(channels))
            )
        await query.message.edit_text(_render(channels), reply_markup=_list_markup(channels))
