"""/info, the three intro buttons, and the channel-gate re-check."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.handlers.start import Registration
from app.bot.keyboards import intro_inline, join_channels_inline, ms_keyboard
from app.config import get_settings
from app.services import channels as channel_service
from app.store.json_store import Store
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
async def recheck_join(
    query: CallbackQuery, user: User, store: Store, state: FSMContext
) -> None:
    """Re-check membership and, if satisfied, carry the user on to where they were.

    Dead-ending on "thanks, you may now use the bot" left people to guess that
    /start was the next step, so this hands them straight to registration or to
    the section keyboard.
    """
    missing = await channel_service.missing_for(query.bot, store, user.id)

    if missing:
        await query.answer(texts.STILL_NOT_JOINED, show_alert=True)
        if query.message:
            await query.message.edit_reply_markup(reply_markup=join_channels_inline(missing))
        return

    await query.answer()
    if not query.message:
        return

    await query.message.edit_text(texts.JOIN_CONFIRMED)

    if user.full_name:
        await query.message.answer(
            texts.GREETING.format(name=user.full_name), reply_markup=intro_inline()
        )
        await query.message.answer(texts.MS_SECTION, reply_markup=ms_keyboard())
    else:
        await state.set_state(Registration.waiting_for_name)
        await query.message.answer(texts.ASK_NAME)
