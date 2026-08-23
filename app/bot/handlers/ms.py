"""The Milliy sertifikat section and its reply keyboard."""

from __future__ import annotations

import time

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import ms_keyboard
from app.config import get_settings

router = Router(name="ms")

_NO_HTTPS_HINT = (
    "⚠️ Mini ilova hozircha sozlanmagan (HTTPS manzil yo'q).\n"
    "Administrator <code>WEBHOOK_BASE</code> qiymatini sozlashi kerak."
)

# A webhook delivery can only be processed by a running process, so a stopped
# site is never observable in here. A very fresh process, however, means the
# site was just woken up (idle stop, deploy or crash) and this message arrived
# during or right after the wake-up — worth pointing at the Mini App URL
# directly in case the student's keyboard is stale.
_PROCESS_STARTED = time.monotonic()
_FRESH_START_SECONDS = 120.0


@router.message(Command("ms"))
async def cmd_ms(message: Message) -> None:
    settings = get_settings()
    text = texts.MS_SECTION
    fresh_start = (time.monotonic() - _PROCESS_STARTED) < _FRESH_START_SECONDS
    if fresh_start and settings.miniapp_base.startswith("https://"):
        text += texts.WAKE_NOTICE.format(url=f"{settings.miniapp_base}/answer")
    await message.answer(text, reply_markup=ms_keyboard())


@router.message(F.text.in_({texts.BTN_CHECK_TEST, texts.BTN_CREATE_TEST}))
async def open_mini_app(message: Message) -> None:
    """Only reached when the Mini App button could not be built as a web_app button.

    With a valid HTTPS base the button opens the Mini App directly and this
    handler never fires.
    """
    settings = get_settings()
    if not settings.miniapp_base.startswith("https://"):
        await message.answer(_NO_HTTPS_HINT)
        return

    page = "answer" if message.text == texts.BTN_CHECK_TEST else "create"
    await message.answer(f"{settings.miniapp_base}/{page}")
