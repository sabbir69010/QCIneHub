"""Public handlers: code lookup, Watch Online, Download."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Settings
from keyboards.user import MovieAction, movie_actions_keyboard, watch_keyboard
from models.movie import Movie
from services.exceptions import FileUnavailableError
from services.movie_service import MovieService
from services.notifications import notify_admins
from services.storage_service import StorageService
from utils.validators import is_valid_code, normalize_code

logger = logging.getLogger(__name__)

router = Router(name="user")
router.message.filter(F.chat.type == "private")

WELCOME = "Welcome to <b>Q Cine Hub</b> 🎬\nPlease enter your movie code."
NOT_FOUND = "❌ Movie code not found.\nPlease check the code and try again."
INVALID_FORMAT = (
    "⚠️ That doesn't look like a valid movie code.\n"
    "Codes use letters and numbers only (example: <code>QC1234</code>)."
)


def _found_text(movie: Movie) -> str:
    text = f"<b>Movie Found ✅</b>\n\n<b>Movie Name:</b> {escape(movie.movie_name)}"
    if movie.description:
        text += f"\n\n{escape(movie.description)}"
    return text + "\n\nChoose an option:"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()  # also aborts any half-finished admin flow
    await message.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer("Send me a movie code (for example <code>QC1234</code>) and I'll find it for you.")


@router.message(F.text, ~F.text.startswith("/"))
async def on_movie_code(message: Message, movie_service: MovieService) -> None:
    code = normalize_code(message.text or "")
    if not is_valid_code(code):
        await message.answer(INVALID_FORMAT)
        return

    movie = await movie_service.get_by_code(code)
    if movie is None:
        logger.info("Code not found: %s (user %s)", code, message.from_user.id if message.from_user else "?")
        await message.answer(NOT_FOUND)
        return

    await message.answer(_found_text(movie), reply_markup=movie_actions_keyboard(movie.movie_code))


@router.callback_query(MovieAction.filter(F.action == "watch"))
async def on_watch(
    call: CallbackQuery,
    callback_data: MovieAction,
    bot: Bot,
    settings: Settings,
    movie_service: MovieService,
) -> None:
    movie = await movie_service.get_by_code(callback_data.code)
    if movie is None:
        await call.answer("❌ This movie is no longer available.", show_alert=True)
        return
    if not movie.online_link:
        await call.answer("⚠️ No streaming link for this movie yet. Try Download instead.", show_alert=True)
        return

    await call.answer()
    try:
        await bot.send_message(
            call.from_user.id,
            f"🍿 <b>{escape(movie.movie_name)}</b>\nTap the button below to watch online.",
            reply_markup=watch_keyboard(movie.online_link),
        )
    except TelegramBadRequest:
        # Telegram refused the URL (malformed/blocked): tell user, alert admins.
        logger.exception("Invalid online_link for %s", movie.movie_code)
        await bot.send_message(call.from_user.id, "⚠️ The streaming link for this movie is broken. We've been notified.")
        await notify_admins(bot, settings.admin_ids, f"⚠️ Broken online link for <code>{escape(movie.movie_code)}</code>.")


@router.callback_query(MovieAction.filter(F.action == "dl"))
async def on_download(
    call: CallbackQuery,
    callback_data: MovieAction,
    bot: Bot,
    settings: Settings,
    movie_service: MovieService,
    storage_service: StorageService,
) -> None:
    movie = await movie_service.get_by_code(callback_data.code)
    if movie is None:
        await call.answer("❌ This movie is no longer available.", show_alert=True)
        return

    await call.answer("📥 Sending your movie…")
    user_id = call.from_user.id
    try:
        await storage_service.send_movie(user_id, movie)
    except FileUnavailableError:
        logger.error("Storage file missing for %s (message %s)", movie.movie_code, movie.file_message_id)
        await bot.send_message(user_id, "⚠️ Sorry, this movie file is temporarily unavailable. Our team has been notified.")
        await notify_admins(
            bot,
            settings.admin_ids,
            f"🚨 File missing for <code>{escape(movie.movie_code)}</code> ({escape(movie.movie_name)}). "
            "Use /editmovie to attach the file again.",
        )
    except TelegramForbiddenError:
        logger.info("User %s blocked the bot before delivery", user_id)
