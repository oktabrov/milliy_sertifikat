"""Tests the user authored: listing, closing, reopening."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.formatting import render_test_row
from app.bot.keyboards import test_admin_inline
from app.db.models import Attempt, Test, User

router = Router(name="mytests")


@router.message(F.text == texts.BTN_MY_TESTS)
@router.message(Command("testlarim"))
async def my_tests(message: Message, session: AsyncSession, user: User) -> None:
    rows = (
        await session.execute(
            select(Test, func.count(Attempt.id))
            .outerjoin(Attempt, Attempt.test_id == Test.id)
            .where(Test.owner_id == user.id)
            .group_by(Test.id)
            .order_by(Test.created_at.desc())
        )
    ).all()

    if not rows:
        await message.answer(texts.NO_TESTS)
        return

    await message.answer(texts.MY_TESTS_HEADER)
    for test, participants in rows:
        await message.answer(
            render_test_row(test, participants),
            reply_markup=test_admin_inline(test.code, test.status),
        )


@router.callback_query(F.data.startswith("test:"))
async def toggle_test(query: CallbackQuery, session: AsyncSession, user: User) -> None:
    _, action, code = (query.data or "").split(":", 2)

    test = (await session.execute(select(Test).where(Test.code == code))).scalar_one_or_none()
    if test is None or test.owner_id != user.id:
        await query.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    test.status = "closed" if action == "close" else "open"
    await session.commit()

    await query.answer()
    if query.message:
        template = texts.TEST_CLOSED_OK if test.status == "closed" else texts.TEST_REOPENED
        await query.message.answer(template.format(title=test.title))
        await query.message.edit_reply_markup(
            reply_markup=test_admin_inline(test.code, test.status)
        )
