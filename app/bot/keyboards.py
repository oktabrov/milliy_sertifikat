"""Reply and inline keyboards."""

from __future__ import annotations

import time

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.bot import texts
from app.config import get_settings
from app.api.tokens import create_token

# Cache-busting stamp baked into every Mini App URL. It changes whenever the
# process restarts - i.e. on every deploy - so Telegram's in-app browser,
# which caches pages by URL and ignores servers that say nothing about cache
# lifetime, is forced to download the new version instead of showing an old
# one. The cost is one extra download per user per deploy.
MINIAPP_VERSION = str(int(time.time()))


def miniapp_url(page: str) -> str:
    """The public URL of a Mini App page, stamped for a fresh fetch."""
    base = get_settings().miniapp_base
    return f"{base}/{page}?v={MINIAPP_VERSION}"


def miniapp_url_with_token(page: str, user_id: int) -> str:
    """Mini App URL with an embedded auth token for the given user."""
    settings = get_settings()
    base = settings.miniapp_base
    token = create_token(user_id, settings.bot_token)
    return f"{base}/{page}?v={MINIAPP_VERSION}&token={token}"


def ms_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard with Test tekshirish / Test yaratish as web_app buttons.

    Using inline buttons (per-message) instead of reply keyboard (per-chat)
    so each user gets a personalized URL with their auth token embedded.
    """
    settings = get_settings()

    if settings.miniapp_base.startswith("https://"):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=texts.BTN_CHECK_TEST,
                    web_app=WebAppInfo(url=miniapp_url_with_token("answer", user_id)),
                )],
                [InlineKeyboardButton(
                    text=texts.BTN_CREATE_TEST,
                    web_app=WebAppInfo(url=miniapp_url_with_token("create", user_id)),
                )],
                [InlineKeyboardButton(
                    text=texts.BTN_MY_RESULTS,
                    callback_data="nav:results",
                )],
                [InlineKeyboardButton(
                    text=texts.BTN_MY_TESTS,
                    callback_data="nav:tests",
                )],
            ]
        )
    # Fallback for local development without HTTPS
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_CHECK_TEST, callback_data="nav:check")],
            [InlineKeyboardButton(text=texts.BTN_CREATE_TEST, callback_data="nav:create")],
            [InlineKeyboardButton(text=texts.BTN_MY_RESULTS, callback_data="nav:results")],
            [InlineKeyboardButton(text=texts.BTN_MY_TESTS, callback_data="nav:tests")],
        ]
    )


def miniapp_inline(page: str, text: str) -> InlineKeyboardMarkup | None:
    """An inline button that opens the Mini App as a real Mini App."""
    if not get_settings().miniapp_base.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, web_app=WebAppInfo(url=miniapp_url(page)))]
        ]
    )


def see_result_inline(test_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_SEE_RESULT, callback_data=f"result:{test_code}")]
        ]
    )


def join_channels_inline(channels: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for channel in channels:
        handle = channel.lstrip("@")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{texts.BTN_JOIN} @{handle}", url=f"https://t.me/{handle}"
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=texts.BTN_CHECK_JOIN, callback_data="join:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def test_admin_inline(test_code: str, status: str) -> InlineKeyboardMarkup:
    if status == "open":
        toggle = InlineKeyboardButton(
            text=texts.BTN_CLOSE_TEST, callback_data=f"test:close:{test_code}"
        )
    else:
        toggle = InlineKeyboardButton(
            text=texts.BTN_REOPEN_TEST, callback_data=f"test:open:{test_code}"
        )
    return InlineKeyboardMarkup(inline_keyboard=[[toggle]])


def submission_notify_inline(test_code: str) -> InlineKeyboardMarkup:
    """Inline buttons sent to the test creator when someone submits."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_CURRENT_STATUS, callback_data=f"leaderboard:{test_code}"
                ),
                InlineKeyboardButton(
                    text=texts.BTN_CLOSE_TEST, callback_data=f"test:close:{test_code}"
                ),
            ]
        ]
    )


def intro_inline() -> InlineKeyboardMarkup:
    """The three intro buttons shown with the /start greeting."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_HOW_TO_ANSWER, callback_data="how:answer")],
            [InlineKeyboardButton(text=texts.BTN_HOW_TO_CREATE, callback_data="how:create")],
            [InlineKeyboardButton(text=texts.BTN_HELP_VIDEO, callback_data="how:video")],
        ]
    )
