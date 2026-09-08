"""Catch-all for anything no other handler claimed.

This router re-sends the intro keyboard whenever the bot receives something it does
not understand — which is exactly what a confused user does next. Included
last, so it only ever runs after every real handler has declined.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import intro_inline

router = Router(name="fallback")


@router.message(F.text)
async def unrecognised_text(message: Message) -> None:
    await message.answer(texts.UNKNOWN, reply_markup=intro_inline())
