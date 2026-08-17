"""The required-channel list, editable at runtime by an admin.

Kept in the store rather than in `.env` so changing it does not need an SSH
session, a file edit and a restart. `REQUIRED_CHANNELS` still seeds the list the
first time, and after that the stored value wins — including when it is empty,
which is why `has_setting` exists: an admin who removes every channel means "no
gate", not "fall back to the environment".
"""

from __future__ import annotations

import re

from app.config import get_settings
from app.store.json_store import Store

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
