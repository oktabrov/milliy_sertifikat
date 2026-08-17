"""Viewing results: the "Mening natijalarim" button and the per-test callback."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.formatting import render_result
from app.db.models import Attempt, Test, User

router = Router(name="results")


async def _send_attempts(target: Message, session: AsyncSession, user: User, limit: int) -> None:
    rows = (
        await session.execute(
            select(Attempt, Test)
            .join(Test, Test.id == Attempt.test_id)
            .where(Attempt.user_id == user.id)
            .order_by(Attempt.submitted_at.desc())
            .limit(limit)
        )
    ).all()

    if not rows:
        await target.answer(texts.NO_RESULTS)
        return

    name = user.full_name or "—"
    for attempt, test in rows:
        if not attempt.results:
            await target.answer(texts.RESULT_PENDING)
            continue
        await target.answer(render_result(attempt, test, name))


@router.message(F.text == texts.BTN_MY_RESULTS)
@router.message(Command("natijalarim"))
async def my_results(message: Message, session: AsyncSession, user: User) -> None:
    await _send_attempts(message, session, user, limit=10)


@router.callback_query(F.data.startswith("result:"))
async def show_result(query: CallbackQuery, session: AsyncSession, user: User) -> None:
    await query.answer()
    code = (query.data or "").split(":", 1)[1]

    row = (
        await session.execute(
            select(Attempt, Test)
            .join(Test, Test.id == Attempt.test_id)
            .where(Attempt.user_id == user.id, Test.code == code)
        )
    ).first()

    if row is None or not query.message:
        return

    attempt, test = row
    if not attempt.results:
        await query.message.answer(texts.RESULT_PENDING)
        return

    await query.message.answer(render_result(attempt, test, user.full_name or "—"))
