"""Middlewares: user record, channel-subscription gate."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from app.bot import texts
from app.bot.keyboards import join_channels_inline
from app.config import get_settings
from app.store.json_store import get_store

logger = logging.getLogger(__name__)

# Commands that must work even for someone who has not joined the channels yet,
# otherwise a new user can get stuck with no way back.
_GATE_EXEMPT_COMMANDS = ("/start", "/info")


class StoreMiddleware(BaseMiddleware):
    """Puts the store and the current user in the handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        store = get_store()
        data["store"] = store
        data["user"] = None

        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is not None and not tg_user.is_bot:
            data["user"] = await store.ensure_user(
                tg_user.id,
                username=tg_user.username,
                is_admin=tg_user.id in get_settings().admin_id_list,
            )

        return await handler(event, data)


class ChannelGateMiddleware(BaseMiddleware):
    """Blocks handlers until the user has joined every required channel.

    Does nothing when REQUIRED_CHANNELS is empty.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        channels = get_settings().required_channel_list
        if not channels:
            return await handler(event, data)

        if isinstance(event, Message):
            text = (event.text or "").strip()
            if any(text.startswith(command) for command in _GATE_EXEMPT_COMMANDS):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if (event.data or "").startswith("join:"):
                return await handler(event, data)

        user = data.get("user")
        if user is None:
            return await handler(event, data)

        missing = await missing_channels(data["bot"], user.id, channels)
        if not missing:
            return await handler(event, data)

        markup = join_channels_inline(missing)
        if isinstance(event, Message):
            await event.answer(texts.MUST_JOIN, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await event.message.answer(texts.MUST_JOIN, reply_markup=markup)
        return None


async def missing_channels(bot, user_id: int, channels: list[str]) -> list[str]:
    """Channels from `channels` the user has not joined.

    A channel we cannot query (bot not an admin there, wrong handle) is treated
    as joined — a misconfiguration should not lock everybody out.
    """
    missing = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        except Exception:
            logger.warning("Cannot check membership for %s; skipping gate", channel)
            continue
        if member.status in ("left", "kicked"):
            missing.append(channel)
    return missing
