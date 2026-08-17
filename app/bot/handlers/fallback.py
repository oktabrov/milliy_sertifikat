"""Catch-all for anything no other handler claimed.

Reply keyboards persist in a chat with the Mini App URL frozen into the button
at the moment they were sent, so after the public address changes every user is
left holding a dead button and no way to discover that typing /ms would fix it.

This router re-sends the keyboard whenever the bot receives something it does
not understand — which is exactly what a confused user does next. Included
last, so it only ever runs after every real handler has declined.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import ms_keyboard

router = Router(name="fallback")


@router.message(F.text)
async def unrecognised_text(message: Message) -> None:
    await message.answer(texts.UNKNOWN, reply_markup=ms_keyboard())
