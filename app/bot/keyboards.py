"""Reply and inline keyboards."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.bot import texts
from app.config import get_settings


def intro_inline() -> InlineKeyboardMarkup:
    """The three buttons shown right after registration."""
    settings = get_settings()
    rows = [
        [InlineKeyboardButton(text=texts.BTN_HOW_TO_ANSWER, callback_data="how:answer")],
        [InlineKeyboardButton(text=texts.BTN_HOW_TO_CREATE, callback_data="how:create")],
        [InlineKeyboardButton(text=texts.BTN_HELP_VIDEO, callback_data="how:video")],
    ]
    if settings.help_video_url:
        rows[2] = [InlineKeyboardButton(text=texts.BTN_HELP_VIDEO, url=settings.help_video_url)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ms_keyboard() -> ReplyKeyboardMarkup:
    """The Milliy sertifikat section keyboard.

    "Test tekshirish" and "Test yaratish" open the Mini App directly. Telegram
    only allows web_app buttons over HTTPS, so when WEBHOOK_BASE is unset (local
    development without a tunnel) they fall back to plain buttons and the
    handlers reply with a link instead.
    """
    settings = get_settings()
    base = settings.miniapp_base

    if base.startswith("https://"):
        check_button = KeyboardButton(
            text=texts.BTN_CHECK_TEST, web_app=WebAppInfo(url=f"{base}/answer")
        )
        create_button = KeyboardButton(
            text=texts.BTN_CREATE_TEST, web_app=WebAppInfo(url=f"{base}/create")
        )
    else:
        check_button = KeyboardButton(text=texts.BTN_CHECK_TEST)
        create_button = KeyboardButton(text=texts.BTN_CREATE_TEST)

    return ReplyKeyboardMarkup(
        keyboard=[
            [check_button],
            [create_button],
            [KeyboardButton(text=texts.BTN_MY_RESULTS)],
            [KeyboardButton(text=texts.BTN_MY_TESTS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Kerakli tugmani bosing",
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
