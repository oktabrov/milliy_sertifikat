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
from app.services import channels as channel_service
from app.store.json_store import get_store

logger = logging.getLogger(__name__)

# The only commands reachable without joining. Everything else — including
# /start and name registration — is gated, so an unsubscribed user can never
# reach a Mini App button in the first place.
#
# The channel commands stay open so an admin who adds a wrong channel is not
# locked out of the commands needed to remove it. They check `is_admin`
# themselves, so this exemption grants an ordinary user nothing.
_GATE_EXEMPT_COMMANDS = (
    "/info",
    "/kanallar",
    "/kanal_qoshish",
    "/kanal_ochirish",
    "/kanal_tozalash",
)


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
    """Blocks every handler until the user has joined *all* required channels.

    Does nothing when no channels are configured.

    Admins are gated exactly like everyone else. Exempting them was convenient
    but meant the owner could never see what a student sees, and made the gate
    untestable from the account most likely to be testing it.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        store = data.get("store") or get_store()
        if not channel_service.current(store):
            return await handler(event, data)

        if isinstance(event, Message):
            text = (event.text or "").strip()
            if any(text.startswith(command) for command in _GATE_EXEMPT_COMMANDS):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if (event.data or "").startswith(("join:", "chan:")):
                return await handler(event, data)

        user = data.get("user")
        if user is None:
            return await handler(event, data)

        missing = await channel_service.missing_for(data["bot"], store, user.id)
        if not missing:
            return await handler(event, data)

        markup = join_channels_inline(missing)
        if isinstance(event, Message):
            await event.answer(texts.MUST_JOIN, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            await event.answer(texts.STILL_NOT_JOINED, show_alert=True)
            if event.message:
                await event.message.answer(texts.MUST_JOIN, reply_markup=markup)
        return None
