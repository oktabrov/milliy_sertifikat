"""Tests the user authored: listing, closing, reopening."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.formatting import render_test_row
from app.bot.keyboards import test_admin_inline
from app.store.json_store import Store
from app.store.models import User

router = Router(name="mytests")


@router.message(F.text == texts.BTN_MY_TESTS)
@router.message(Command("testlarim"))
async def my_tests(message: Message, store: Store, user: User) -> None:
    tests = store.tests_by_owner(user.id)
    if not tests:
        await message.answer(texts.NO_TESTS)
        return

    await message.answer(texts.MY_TESTS_HEADER)
    for test in tests:
        await message.answer(
            render_test_row(test, store.count_attempts(test.id)),
            reply_markup=test_admin_inline(test.code, test.status),
        )


@router.callback_query(F.data.startswith("test:"))
async def toggle_test(query: CallbackQuery, store: Store, user: User) -> None:
    _, action, code = (query.data or "").split(":", 2)

    test = store.get_test_by_code(code)
    if test is None or test.owner_id != user.id:
        await query.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    test.status = "closed" if action == "close" else "open"
    await store.save_test(test)

    await query.answer()
    if query.message:
        template = texts.TEST_CLOSED_OK if test.status == "closed" else texts.TEST_REOPENED
        await query.message.answer(template.format(title=test.title))
        await query.message.edit_reply_markup(
            reply_markup=test_admin_inline(test.code, test.status)
        )
