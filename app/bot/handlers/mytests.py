"""Tests the user authored: listing, closing, reopening, leaderboard."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.formatting import render_leaderboard, render_test_row
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


@router.callback_query(lambda q: q.data == "nav:tests")
async def nav_tests(query: CallbackQuery, store: Store, user: User) -> None:
    await query.answer()
    if not query.message:
        return
    tests = store.tests_by_owner(user.id)
    if not tests:
        await query.message.answer(texts.NO_TESTS)
        return

    await query.message.answer(texts.MY_TESTS_HEADER)
    for test in tests:
        await query.message.answer(
            render_test_row(test, store.count_attempts(test.id)),
            reply_markup=test_admin_inline(test.code, test.status),
        )


@router.callback_query(F.data.startswith("leaderboard:"))
async def show_leaderboard(query: CallbackQuery, store: Store, user: User) -> None:
    """Show the current leaderboard without changing anything."""
    await query.answer()
    code = (query.data or "").split(":", 1)[1]

    test = store.get_test_by_code(code)
    if test is None or not query.message:
        return

    attempts = store.attempts_by_test(test.id)
    owner = store.get_user(test.owner_id)
    owner_name = (owner.full_name if owner else None) or "—"

    # Build user name map
    user_names: dict[int, str] = {}
    for attempt in attempts:
        u = store.get_user(attempt.user_id)
        if u:
            user_names[u.id] = u.full_name or u.username or f"ID:{u.id}"

    await query.message.answer(render_leaderboard(test, attempts, owner_name, user_names))


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

    # Send leaderboard when test is closed
    if test.status == "closed":
        attempts = store.attempts_by_test(test.id)
        if attempts:
            owner = store.get_user(test.owner_id)
            owner_name = (owner.full_name if owner else None) or "—"

            user_names: dict[int, str] = {}
            for attempt in attempts:
                u = store.get_user(attempt.user_id)
                if u:
                    user_names[u.id] = u.full_name or u.username or f"ID:{u.id}"

            if query.message:
                await query.message.answer(
                    render_leaderboard(test, attempts, owner_name, user_names)
                )
