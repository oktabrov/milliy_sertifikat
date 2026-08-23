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


def ms_keyboard() -> ReplyKeyboardMarkup:
    """The Milliy sertifikat section keyboard.

    The three intro buttons (how to answer, how to create, the video) live at
    the top of this keyboard rather than in a separate inline message, so a
    fresh /start needs to send only one bubble.

    "Test tekshirish" and "Test yaratish" open the Mini App directly. Telegram
    only allows web_app buttons over HTTPS, so when WEBHOOK_BASE is unset (local
    development without a tunnel) they fall back to plain buttons and the
    handlers reply with a link instead.
    """
    settings = get_settings()
    base = settings.miniapp_base

    if base.startswith("https://"):
        check_button = KeyboardButton(
            text=texts.BTN_CHECK_TEST, web_app=WebAppInfo(url=miniapp_url("answer"))
        )
        create_button = KeyboardButton(
            text=texts.BTN_CREATE_TEST, web_app=WebAppInfo(url=miniapp_url("create"))
        )
    else:
        check_button = KeyboardButton(text=texts.BTN_CHECK_TEST)
        create_button = KeyboardButton(text=texts.BTN_CREATE_TEST)

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_HOW_TO_ANSWER)],
            [KeyboardButton(text=texts.BTN_HOW_TO_CREATE)],
            [KeyboardButton(text=texts.BTN_HELP_VIDEO)],
            [check_button],
            [create_button],
            [KeyboardButton(text=texts.BTN_MY_RESULTS)],
            [KeyboardButton(text=texts.BTN_MY_TESTS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Kerakli tugmani bosing",
    )


def miniapp_inline(page: str, text: str) -> InlineKeyboardMarkup | None:
    """An inline button that opens the Mini App as a real Mini App.

    A bare https link opens Telegram's in-app browser instead, where the page
    loads without `initData` and every API call is refused — the trap students
    hit by tapping an old message link and then losing a filled answer sheet.
    Only `web_app` buttons get a Telegram session attached to the page.
    """
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
