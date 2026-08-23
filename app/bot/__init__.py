"""Bot and dispatcher construction."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.bot.middlewares import ChannelGateMiddleware, StoreMiddleware
from app.config import get_settings

BOT_COMMANDS = [
    BotCommand(command="edit", description="Ismni o'zgartirish uchun bosing"),
    BotCommand(command="info", description="Bot ishlatish haqida ma'lumotlar"),
    BotCommand(command="ms", description="Milliy sertifikat bo'limi"),
    BotCommand(command="testlarim", description="Testlaringiz haqida ma'lumotlar"),
    BotCommand(command="natijalarim", description="Sizning natijalaringiz"),
    BotCommand(command="special", description="Admin buyruqlari ro'yxati (admin)"),
    BotCommand(command="kanallar", description="Majburiy kanallar (admin)"),
    BotCommand(command="adminlar", description="Adminlar ro'yxati (admin)"),
    BotCommand(command="id", description="Telegram ID raqamingiz"),
]


def create_bot() -> Bot:
    return Bot(
        token=get_settings().bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    from app.bot.handlers import admin, channels, fallback, info, ms, mytests, results, start

    dispatcher = Dispatcher(storage=MemoryStorage())

    # Order matters: the store middleware populates `user`, which the channel
    # gate then reads.
    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.middleware(StoreMiddleware())
        observer.middleware(ChannelGateMiddleware())

    dispatcher.include_router(start.router)
    dispatcher.include_router(info.router)
    dispatcher.include_router(ms.router)
    dispatcher.include_router(results.router)
    dispatcher.include_router(mytests.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(channels.router)
    # Last: it claims any text nothing else wanted, and re-sends the keyboard.
    dispatcher.include_router(fallback.router)

    return dispatcher


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
