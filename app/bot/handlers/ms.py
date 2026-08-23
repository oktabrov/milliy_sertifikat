"""The Milliy sertifikat section and its reply keyboard."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import ms_keyboard
from app.config import get_settings

router = Router(name="ms")

_NO_HTTPS_HINT = (
    "\u26a0\ufe0f Mini ilova hozircha sozlanmagan (HTTPS manzil yo\u2019q).\n"
    "Administrator <code>WEBHOOK_BASE</code> qiymatini sozlashi kerak."
)


@router.message(Command("ms"))
async def cmd_ms(message: Message) -> None:
    await message.answer(texts.MS_SECTION, reply_markup=ms_keyboard())


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
