"""Q Cine Hub bot entry point.  Run:  python bot.py"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from config import ConfigError, Settings, load_settings
from database import Database
from handlers import build_root_router
from handlers.errors import on_error
from middleware.throttling import ThrottlingMiddleware
from services.exceptions import DatabaseUnavailableError
from services.movie_service import MovieService
from services.storage_service import StorageService
from utils.logging_config import setup_logging

logger = logging.getLogger("qcine")

USER_COMMANDS = [BotCommand(command="start", description="Start the bot")]
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="addmovie", description="Add a movie"),
    BotCommand(command="editmovie", description="Edit a movie"),
    BotCommand(command="deletemovie", description="Delete a movie"),
    BotCommand(command="listmovies", description="List movies"),
    BotCommand(command="cancel", description="Cancel current action"),
]


async def _set_commands(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError:
            logger.warning("Could not set admin commands for %s (has the admin started the bot?)", admin_id)


async def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings.log_dir, settings.log_level)

    db = Database(settings.db_path)
    try:
        await db.connect()
    except DatabaseUnavailableError:
        logger.critical("Cannot start: database unavailable", exc_info=True)
        sys.exit(1)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(
        storage=MemoryStorage(),
        settings=settings,
        movie_service=MovieService(db),
        storage_service=StorageService(bot, settings.storage_chat_id),
    )

    throttle = ThrottlingMiddleware(settings.throttle_seconds)
    dp.message.outer_middleware(throttle)
    dp.callback_query.outer_middleware(throttle)
    dp.include_router(build_root_router(settings))
    dp.errors.register(on_error)

    try:
        me = await bot.get_me()
        logger.info("Starting @%s", me.username)
        try:
            chat = await bot.get_chat(settings.storage_chat_id)
            logger.info("Storage chat OK: %s", chat.title)
        except TelegramAPIError:
            logger.error("Cannot access STORAGE_CHAT_ID=%s - is the bot an admin there?", settings.storage_chat_id)
        await _set_commands(bot, settings)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
