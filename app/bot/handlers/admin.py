"""Admin commands: /stats and /broadcast."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db.models import Attempt, Test, User

logger = logging.getLogger(__name__)
router = Router(name="admin")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession, user: User) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    users = await session.scalar(select(func.count(User.id)))
    tests = await session.scalar(select(func.count(Test.id)))
    attempts = await session.scalar(select(func.count(Attempt.id)))

    await message.answer(texts.ADMIN_STATS.format(users=users, tests=tests, attempts=attempts))


@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: Message, command: CommandObject, session: AsyncSession, user: User
) -> None:
    if not user.is_admin:
        await message.answer(texts.ADMIN_ONLY)
        return

    body = (command.args or "").strip()
    if not body:
        await message.answer(texts.BROADCAST_USAGE)
        return

    ids = (await session.execute(select(User.id).where(User.is_blocked.is_(False)))).scalars().all()

    sent = 0
    failed = 0
    for index, chat_id in enumerate(ids):
        try:
            await message.bot.send_message(chat_id, body)
            sent += 1
        except Exception:
            failed += 1
        # Telegram tolerates roughly 30 messages a second to distinct chats.
        if index % 25 == 24:
            await asyncio.sleep(1)

    await message.answer(texts.BROADCAST_DONE.format(sent=sent, failed=failed))
