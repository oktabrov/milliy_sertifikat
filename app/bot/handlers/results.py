"""Viewing results: the "Mening natijalarim" button and the per-test callback."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.formatting import render_result
from app.store.json_store import Store
from app.store.models import User

router = Router(name="results")


@router.message(F.text == texts.BTN_MY_RESULTS)
@router.message(Command("natijalarim"))
async def my_results(message: Message, store: Store, user: User) -> None:
    attempts = store.attempts_by_user(user.id, limit=5)
    if not attempts:
        await message.answer(texts.NO_RESULTS)
        return

    name = user.full_name or "—"
    for attempt in attempts:
        test = store.get_test(attempt.test_id)
        if test is None:
            continue
        if not attempt.results:
            await message.answer(texts.RESULT_PENDING)
            continue
        await message.answer(render_result(attempt, test, name))


@router.callback_query(lambda q: q.data == "nav:results")
async def nav_results(query: CallbackQuery, store: Store, user: User) -> None:
    await query.answer()
    if not query.message:
        return
    attempts = store.attempts_by_user(user.id, limit=5)
    if not attempts:
        await query.message.answer(texts.NO_RESULTS)
        return

    name = user.full_name or "—"
    for attempt in attempts:
        test = store.get_test(attempt.test_id)
        if test is None:
            continue
        if not attempt.results:
            await query.message.answer(texts.RESULT_PENDING)
            continue
        await query.message.answer(render_result(attempt, test, name))


@router.callback_query(F.data.startswith("result:"))
async def show_result(query: CallbackQuery, store: Store, user: User) -> None:
    await query.answer()
    code = (query.data or "").split(":", 1)[1]

    test = store.get_test_by_code(code)
    if test is None or not query.message:
        return

    attempt = store.get_attempt(test.id, user.id)
    if attempt is None:
        return

    if not attempt.results:
        await query.message.answer(texts.RESULT_PENDING)
        return

    await query.message.answer(render_result(attempt, test, user.full_name or "—"))
