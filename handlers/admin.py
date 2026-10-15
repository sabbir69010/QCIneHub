"""Admin panel: /addmovie /editmovie /deletemovie /listmovies."""
from __future__ import annotations

import logging
import math
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from handlers.states import AddMovie, DeleteMovie, EditMovie
from keyboards.admin import (
    DeleteConfirm, EditField, ListPage,
    delete_confirm_keyboard, edit_fields_keyboard, list_keyboard,
)
from models.movie import Movie
from services.exceptions import (
    DatabaseUnavailableError, DuplicateMovieCodeError, UnsupportedFileError,
)
from services.movie_service import MovieService
from services.storage_service import StorageService, storage_caption
from utils.validators import (
    CODE_RULES, clean_description, clean_name, clean_url, is_valid_code, normalize_code,
)

logger = logging.getLogger(__name__)

# AdminOnlyMiddleware is attached in handlers/__init__.py
router = Router(name="admin")
router.message.filter(F.chat.type == "private")

PAGE_SIZE = 10
CANCEL = "\n\n<i>Send /cancel to abort.</i>"
NOT_COMMAND = ~F.text.startswith("/")
FILE_HELP = "📎 Please forward or send the movie as a <b>video</b> or <b>document</b>."


def movie_summary(movie: Movie) -> str:
    file_line = f"✅ stored (message {movie.file_message_id})" if movie.has_file else "❌ missing"
    return (
        f"🎬 <b>{escape(movie.movie_name)}</b>\n"
        f"Code: <code>{escape(movie.movie_code)}</code>\n"
        f"Description: {escape(movie.description) if movie.description else '—'}\n"
        f"Online link: {escape(movie.online_link) if movie.online_link else '—'}\n"
        f"File: {file_line}\n"
        f"Added: {movie.added_date}"
    )


# ----------------------------------------------------------------- misc
@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "🛠 <b>Admin panel</b>\n\n"
        "/addmovie — add a movie\n"
        "/editmovie [code] — edit a movie\n"
        "/deletemovie [code] — delete a movie\n"
        "/listmovies — list all movies\n"
        "/cancel — abort the current flow"
    )


# Registered first so it wins over the state handlers below.
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Nothing to cancel.")
        return
    await state.clear()
    await message.answer("❌ Cancelled.")


# ------------------------------------------------------------ /addmovie
@router.message(Command("addmovie"))
async def add_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddMovie.code)
    await message.answer(
        "➕ <b>Add movie</b>\n\nStep 1/5 — send the <b>movie code</b> (e.g. <code>QC1234</code>)." + CANCEL
    )


@router.message(AddMovie.code, F.text, NOT_COMMAND)
async def add_code(message: Message, state: FSMContext, movie_service: MovieService) -> None:
    code = normalize_code(message.text or "")
    if not is_valid_code(code):
        await message.answer(CODE_RULES)
        return
    if await movie_service.get_by_code(code):
        await message.answer(f"⚠️ Code <code>{escape(code)}</code> already exists. Send a different code.")
        return
    await state.update_data(movie_code=code)
    await state.set_state(AddMovie.name)
    await message.answer("Step 2/5 — send the <b>movie name</b>." + CANCEL)


@router.message(AddMovie.name, F.text, NOT_COMMAND)
async def add_name(message: Message, state: FSMContext) -> None:
    name = clean_name(message.text or "")
    if name is None:
        await message.answer("⚠️ Name must be 1–100 characters. Try again.")
        return
    await state.update_data(movie_name=name)
    await state.set_state(AddMovie.description)
    await message.answer("Step 3/5 — send the <b>description</b> (or <code>-</code> for none)." + CANCEL)


@router.message(AddMovie.description, F.text, NOT_COMMAND)
async def add_description(message: Message, state: FSMContext) -> None:
    description = clean_description(message.text or "")
    if description is None:
        await message.answer("⚠️ Description must be at most 600 characters. Try again.")
        return
    await state.update_data(description=description)
    await state.set_state(AddMovie.link)
    await message.answer(
        "Step 4/5 — send the <b>online (streaming) link</b> starting with http(s)://, "
        "or <code>-</code> to skip." + CANCEL
    )


@router.message(AddMovie.link, F.text, NOT_COMMAND)
async def add_link(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    link: str | None = None
    if raw != "-":
        link = clean_url(raw)
        if link is None:
            await message.answer("⚠️ That isn't a valid http(s) URL. Send a valid link or <code>-</code>.")
            return
    await state.update_data(online_link=link)
    await state.set_state(AddMovie.file)
    await message.answer("Step 5/5 — <b>forward or send the movie file</b>." + CANCEL)


@router.message(AddMovie.file, F.video | F.document)
async def add_file(
    message: Message, state: FSMContext, movie_service: MovieService, storage_service: StorageService
) -> None:
    data = await state.get_data()
    code: str = data["movie_code"]
    name: str = data["movie_name"]

    try:
        stored = await storage_service.ingest(message, storage_caption(code, name))
    except UnsupportedFileError:
        await message.answer(FILE_HELP)
        return
    except TelegramAPIError as exc:
        logger.exception("Failed to store file in storage channel")
        await message.answer(
            f"❌ Could not store the file in the storage channel: <code>{escape(str(exc))}</code>\n"
            "Check that the bot is an <b>admin</b> of that channel with permission to post."
        )
        return

    try:
        movie = await movie_service.create(
            movie_code=code,
            movie_name=name,
            description=data.get("description", ""),
            online_link=data.get("online_link"),
            file_message_id=stored.message_id,
            file_id=stored.file_id,
            file_unique_id=stored.file_unique_id,
            file_name=stored.file_name,
            file_size=stored.file_size,
        )
    except DuplicateMovieCodeError:
        if stored.copied:
            await storage_service.delete_stored(stored.message_id)
        await state.clear()
        await message.answer(f"⚠️ Code <code>{escape(code)}</code> was just taken. Start again with /addmovie.")
        return
    except DatabaseUnavailableError:
        if stored.copied:
            await storage_service.delete_stored(stored.message_id)  # avoid orphans
        raise  # global error handler informs the admin

    await state.clear()
    await message.answer("✅ <b>Movie added</b>\n\n" + movie_summary(movie))


@router.message(AddMovie.file)
async def add_file_wrong_type(message: Message) -> None:
    await message.answer(FILE_HELP)


# ----------------------------------------------------------- /editmovie
async def _show_edit_menu(message: Message, movie_service: MovieService, raw_code: str) -> bool:
    code = normalize_code(raw_code)
    movie = await movie_service.get_by_code(code) if is_valid_code(code) else None
    if movie is None:
        await message.answer("❌ Movie code not found. Send another code.")
        return False
    await message.answer(
        movie_summary(movie) + "\n\nWhat do you want to edit?",
        reply_markup=edit_fields_keyboard(movie.movie_code),
    )
    return True


@router.message(Command("editmovie"))
async def edit_start(
    message: Message, command: CommandObject, state: FSMContext, movie_service: MovieService
) -> None:
    await state.clear()
    if command.args:
        await _show_edit_menu(message, movie_service, command.args.split()[0])
        return
    await state.set_state(EditMovie.code)
    await message.answer("✏️ <b>Edit movie</b>\n\nSend the movie code." + CANCEL)


@router.message(EditMovie.code, F.text, NOT_COMMAND)
async def edit_code(message: Message, state: FSMContext, movie_service: MovieService) -> None:
    if await _show_edit_menu(message, movie_service, message.text or ""):
        await state.clear()


@router.callback_query(EditField.filter(F.field == "close"))
async def edit_close(call: CallbackQuery) -> None:
    await call.answer()
    if isinstance(call.message, Message):
        await call.message.delete()


@router.callback_query(EditField.filter())
async def edit_pick_field(
    call: CallbackQuery, callback_data: EditField, state: FSMContext, movie_service: MovieService
) -> None:
    movie = await movie_service.get_by_code(callback_data.code)
    if movie is None:
        await call.answer("Movie no longer exists.", show_alert=True)
        return
    prompts = {
        "name": "Send the new <b>movie name</b>.",
        "description": "Send the new <b>description</b> (or <code>-</code> to clear).",
        "link": "Send the new <b>online link</b> (or <code>-</code> to remove).",
        "file": "Forward or send the <b>new movie file</b>.",
    }
    if callback_data.field not in prompts:
        await call.answer()
        return
    await state.set_state(EditMovie.value)
    await state.update_data(code=movie.movie_code, field=callback_data.field)
    await call.answer()
    if isinstance(call.message, Message):
        await call.message.answer(prompts[callback_data.field] + CANCEL)


@router.message(EditMovie.value, F.text, NOT_COMMAND)
async def edit_apply_text(message: Message, state: FSMContext, movie_service: MovieService) -> None:
    data = await state.get_data()
    code, field = data["code"], data["field"]
    raw = message.text or ""

    if field == "name":
        name = clean_name(raw)
        if name is None:
            await message.answer("⚠️ Name must be 1–100 characters. Try again.")
            return
        updates: dict[str, object] = {"movie_name": name}
    elif field == "description":
        description = clean_description(raw)
        if description is None:
            await message.answer("⚠️ Description must be at most 600 characters. Try again.")
            return
        updates = {"description": description}
    elif field == "link":
        if raw.strip() == "-":
            updates = {"online_link": None}
        else:
            url = clean_url(raw)
            if url is None:
                await message.answer("⚠️ That isn't a valid http(s) URL. Try again or send <code>-</code>.")
                return
            updates = {"online_link": url}
    else:
        await message.answer(FILE_HELP)
        return

    updated = await movie_service.update(code, **updates)
    await state.clear()
    await message.answer("✅ Updated." if updated else "❌ That movie no longer exists.")


@router.message(EditMovie.value, F.video | F.document)
async def edit_apply_file(
    message: Message, state: FSMContext, movie_service: MovieService, storage_service: StorageService
) -> None:
    data = await state.get_data()
    if data.get("field") != "file":
        await message.answer("Please send text for this field, not a file.")
        return

    movie = await movie_service.get_by_code(data["code"])
    if movie is None:
        await state.clear()
        await message.answer("❌ That movie no longer exists.")
        return

    try:
        stored = await storage_service.ingest(message, storage_caption(movie.movie_code, movie.movie_name))
    except TelegramAPIError as exc:
        logger.exception("Failed to store replacement file")
        await message.answer(f"❌ Could not store the file: <code>{escape(str(exc))}</code>")
        return

    try:
        await movie_service.update(
            movie.movie_code,
            file_message_id=stored.message_id,
            file_id=stored.file_id,
            file_unique_id=stored.file_unique_id,
            file_name=stored.file_name,
            file_size=stored.file_size,
        )
    except DatabaseUnavailableError:
        if stored.copied:
            await storage_service.delete_stored(stored.message_id)
        raise

    # The previous file is deliberately left in the storage channel (never auto-deleted).
    await state.clear()
    await message.answer("✅ Movie file replaced.")


@router.message(EditMovie.value)
async def edit_value_wrong_type(message: Message) -> None:
    await message.answer("Please send the value as text (or the file, if you chose “Movie file”).")


# --------------------------------------------------------- /deletemovie
async def _ask_delete_confirmation(message: Message, movie_service: MovieService, raw_code: str) -> bool:
    code = normalize_code(raw_code)
    movie = await movie_service.get_by_code(code) if is_valid_code(code) else None
    if movie is None:
        await message.answer("❌ Movie code not found. Send another code.")
        return False
    await message.answer(
        movie_summary(movie)
        + "\n\n⚠️ <b>Delete this movie?</b>\n<i>The record is removed; the file stays in your storage channel.</i>",
        reply_markup=delete_confirm_keyboard(movie.movie_code),
    )
    return True


@router.message(Command("deletemovie"))
async def delete_start(
    message: Message, command: CommandObject, state: FSMContext, movie_service: MovieService
) -> None:
    await state.clear()
    if command.args:
        await _ask_delete_confirmation(message, movie_service, command.args.split()[0])
        return
    await state.set_state(DeleteMovie.code)
    await message.answer("🗑 <b>Delete movie</b>\n\nSend the movie code." + CANCEL)


@router.message(DeleteMovie.code, F.text, NOT_COMMAND)
async def delete_code(message: Message, state: FSMContext, movie_service: MovieService) -> None:
    if await _ask_delete_confirmation(message, movie_service, message.text or ""):
        await state.clear()


async def _replace_message(call: CallbackQuery, text: str) -> None:
    await call.answer()
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(text)
        except TelegramBadRequest:
            await call.message.answer(text)


@router.callback_query(DeleteConfirm.filter())
async def delete_confirm(
    call: CallbackQuery, callback_data: DeleteConfirm, movie_service: MovieService
) -> None:
    if callback_data.action != "yes":
        await _replace_message(call, "↩️ Deletion cancelled.")
        return
    deleted = await movie_service.delete(callback_data.code)
    await _replace_message(
        call,
        f"🗑 Movie <code>{escape(callback_data.code)}</code> deleted." if deleted else "❌ That movie no longer exists.",
    )


# ---------------------------------------------------------- /listmovies
async def _render_list(movie_service: MovieService, page: int) -> tuple[str, InlineKeyboardMarkup]:
    total = await movie_service.count()
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(page, 1), pages)
    movies = await movie_service.list_page(offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE)

    if not movies:
        body = "📭 No movies yet. Use /addmovie."
    else:
        body = "\n".join(
            f"<code>{escape(m.movie_code)}</code> — {escape(m.movie_name)} "
            f"{'🎞' if m.has_file else '❌file'} {'🔗' if m.has_link else ''}"
            for m in movies
        )
    text = f"🎞 <b>Movies</b> ({total}) — page {page}/{pages}\n\n{body}"
    return text, list_keyboard(page, pages)


@router.message(Command("listmovies"))
async def list_movies(message: Message, movie_service: MovieService) -> None:
    text, keyboard = await _render_list(movie_service, 1)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(ListPage.filter())
async def list_page(call: CallbackQuery, callback_data: ListPage, movie_service: MovieService) -> None:
    text, keyboard = await _render_list(movie_service, callback_data.page)
    await call.answer()
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            pass  # "message is not modified" when the same page is re-selected
