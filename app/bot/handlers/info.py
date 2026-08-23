"""/info, the three intro buttons, and the channel-gate re-check."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.handlers.start import Registration
from app.bot.keyboards import join_channels_inline, ms_keyboard
from app.services import channels as channel_service
from app.services import video as video_service
from app.store.json_store import Store
from app.store.models import User

router = Router(name="info")


@router.message(Command("info"))
async def cmd_info(message: Message) -> None:
    await message.answer(texts.INFO)


@router.message(F.text == texts.BTN_HOW_TO_ANSWER)
async def how_to_answer(message: Message) -> None:
    await message.answer(texts.HOW_TO_ANSWER)


@router.message(F.text == texts.BTN_HOW_TO_CREATE)
async def how_to_create(message: Message) -> None:
    await message.answer(texts.HOW_TO_CREATE)


@router.message(F.text == texts.BTN_HELP_VIDEO)
async def help_video_message(message: Message, store: Store) -> None:
    await _send_video(message, store)


# Kept for keyboards sent before the intro buttons moved into the reply
# keyboard; those old inline buttons still work.
@router.callback_query(lambda query: query.data == "how:answer")
async def how_to_answer_callback(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await query.message.answer(texts.HOW_TO_ANSWER)


@router.callback_query(lambda query: query.data == "how:create")
async def how_to_create_callback(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await query.message.answer(texts.HOW_TO_CREATE)


@router.callback_query(lambda query: query.data == "how:video")
async def help_video(query: CallbackQuery, store: Store) -> None:
    await query.answer()
    if not query.message:
        return
    await _send_video(query.message, store)


async def _send_video(message: Message, store: Store) -> None:
    """The configured video: a link wins over a stored file, else an apology."""
    url, file_id = video_service.current(store)
    if url:
        await message.answer(url)
    elif file_id:
        await message.answer_video(file_id)
    else:
        await message.answer(texts.HELP_VIDEO_MISSING)


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
            texts.GREETING.format(name=user.full_name), reply_markup=ms_keyboard()
        )
    else:
        await state.set_state(Registration.waiting_for_name)
        await query.message.answer(texts.ASK_NAME)
