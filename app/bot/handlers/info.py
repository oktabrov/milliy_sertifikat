"""/info, the three intro buttons, and the channel-gate re-check."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.keyboards import join_channels_inline
from app.bot.middlewares import missing_channels
from app.config import get_settings
from app.store.models import User

router = Router(name="info")


@router.message(Command("info"))
async def cmd_info(message: Message) -> None:
    await message.answer(texts.INFO)


@router.callback_query(lambda query: query.data == "how:answer")
async def how_to_answer(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await query.message.answer(texts.HOW_TO_ANSWER)


@router.callback_query(lambda query: query.data == "how:create")
async def how_to_create(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await query.message.answer(texts.HOW_TO_CREATE)


@router.callback_query(lambda query: query.data == "how:video")
async def help_video(query: CallbackQuery) -> None:
    settings = get_settings()
    await query.answer()
    if not query.message:
        return
    if settings.help_video_url:
        await query.message.answer(settings.help_video_url)
    else:
        await query.message.answer(texts.HELP_VIDEO_MISSING)


@router.callback_query(lambda query: query.data == "join:check")
async def recheck_join(query: CallbackQuery, user: User) -> None:
    channels = get_settings().required_channel_list
    missing = await missing_channels(query.bot, user.id, channels) if channels else []

    if missing:
        await query.answer(texts.STILL_NOT_JOINED, show_alert=True)
        if query.message:
            await query.message.edit_reply_markup(reply_markup=join_channels_inline(missing))
        return

    await query.answer()
    if query.message:
        await query.message.edit_text(texts.JOIN_CONFIRMED)
