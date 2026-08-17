"""The required-channel list, editable at runtime by an admin.

Kept in the store rather than in `.env` so changing it does not need an SSH
session, a file edit and a restart. `REQUIRED_CHANNELS` still seeds the list the
first time, and after that the stored value wins — including when it is empty,
which is why `has_setting` exists: an admin who removes every channel means "no
gate", not "fall back to the environment".
"""

from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.store.json_store import Store

logger = logging.getLogger(__name__)

SETTING_KEY = "required_channels"

# @name, name, t.me/name, https://t.me/name, or a numeric -100… chat id.
_LINK = re.compile(r"^(?:https?://)?(?:www\.)?t(?:elegram)?\.me/(?:s/)?([A-Za-z0-9_]+)/?$")
_USERNAME = re.compile(r"^@?([A-Za-z0-9_]{4,32})$")


class ChannelError(ValueError):
    """The text the admin sent is not a usable channel reference."""


def normalize(raw: str) -> str:
    """Canonical form: `@username`, or `-100…` for a private channel id."""
    text = (raw or "").strip()
    if not text:
        raise ChannelError("empty")

    if re.fullmatch(r"-100\d{5,}", text):
        return text

    match = _LINK.match(text)
    if match:
        return f"@{match.group(1)}"

    match = _USERNAME.match(text)
    if match:
        return f"@{match.group(1)}"

    raise ChannelError(text)


def current(store: Store) -> list[str]:
    """The channels a student must join. Empty list means no gate."""
    if store.has_setting(SETTING_KEY):
        stored = store.get_setting(SETTING_KEY) or []
        return [str(item) for item in stored]
    return get_settings().required_channel_list


async def add(store: Store, raw: str) -> tuple[list[str], str]:
    """Add a channel. Returns the new list and the canonical name added."""
    channel = normalize(raw)
    channels = current(store)
    if channel.lower() not in {item.lower() for item in channels}:
        channels = channels + [channel]
        await store.set_setting(SETTING_KEY, channels)
    return channels, channel


async def remove(store: Store, raw: str) -> tuple[list[str], bool]:
    """Remove a channel. Returns the new list and whether anything was removed."""
    try:
        channel = normalize(raw)
    except ChannelError:
        channel = (raw or "").strip()

    channels = current(store)
    remaining = [item for item in channels if item.lower() != channel.lower()]
    removed = len(remaining) != len(channels)
    if removed:
        await store.set_setting(SETTING_KEY, remaining)
    return remaining, removed


async def clear(store: Store) -> None:
    """Remove every channel — an explicit "no gate", not a fallback to .env."""
    await store.set_setting(SETTING_KEY, [])


# Statuses that count as being in the channel. "restricted" members are still
# subscribers; "left" and "kicked" are not.
_JOINED = ("creator", "administrator", "member", "restricted")


async def missing_for(bot, store: Store, user_id: int) -> list[str]:
    """Which required channels this user has not joined.

    Empty list means every requirement is satisfied — all channels must be,
    not merely one of them.

    Fails **closed**: a channel that cannot be checked counts as not joined.
    The opposite was tempting (a misconfiguration then locks nobody out) but it
    means a bot that has been removed as channel admin silently stops enforcing
    anything, which is exactly the failure this gate exists to prevent. One
    retry absorbs a transient network blip before refusing.
    """
    channels = current(store)
    if not channels:
        return []

    missing: list[str] = []
    for channel in channels:
        joined = False
        for attempt in range(2):
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            except Exception as error:
                if attempt == 0:
                    continue
                logger.warning(
                    "Cannot verify %s for user %s (%s); treating as not joined",
                    channel,
                    user_id,
                    error,
                )
                break
            joined = member.status in _JOINED
            break
        if not joined:
            missing.append(channel)

    return missing
