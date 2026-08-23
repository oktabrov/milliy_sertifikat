"""Registration: /start asks for a name, /edit changes it."""

from __future__ import annotations

import re

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import ms_keyboard
from app.store.json_store import Store
from app.store.models import User

router = Router(name="start")

# Latin letters, apostrophes (o' and g' are ordinary Uzbek letters), hyphens,
# spaces and dots. Cyrillic is rejected on purpose — the prompt asks for Latin.
_NAME_PATTERN = re.compile(r"^[A-Za-z'’`\-. ]+$")


class Registration(StatesGroup):
    waiting_for_name = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    if user.full_name:
        await message.answer(
            texts.GREETING.format(name=user.full_name), reply_markup=ms_keyboard()
        )
        return
    await state.set_state(Registration.waiting_for_name)
    await message.answer(texts.ASK_NAME)


@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext) -> None:
    await state.set_state(Registration.waiting_for_name)
    await message.answer(texts.ASK_NAME)


@router.message(Registration.waiting_for_name, F.text)
async def receive_name(message: Message, state: FSMContext, user: User, store: Store) -> None:
    name = " ".join((message.text or "").split())

    if len(name) < 5:
        await message.answer(texts.NAME_TOO_SHORT)
        return
    if not _NAME_PATTERN.match(name):
        await message.answer(texts.NAME_NOT_LATIN)
        return

    was_registered = bool(user.full_name)
    user.full_name = name.title()
    await store.save_user(user)
    await state.clear()

    if was_registered:
        await message.answer(
            texts.NAME_UPDATED.format(name=user.full_name), reply_markup=ms_keyboard()
        )
        return

    await message.answer(
        texts.GREETING.format(name=user.full_name), reply_markup=ms_keyboard()
    )
