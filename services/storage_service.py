"""Everything that touches the private storage channel."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message, MessageOriginChannel

from models.movie import Movie
from services.exceptions import FileUnavailableError, UnsupportedFileError

logger = logging.getLogger(__name__)

# Substrings of Telegram error descriptions meaning "that message no longer exists".
_GONE_MARKERS = (
    "message to copy not found",
    "message to forward not found",
    "message_id_invalid",
    "message can't be copied",
)


@dataclass(frozen=True, slots=True)
class StoredFile:
    message_id: int          # message ID inside the storage channel
    copied: bool             # True if the bot created that message itself
    file_id: str | None
    file_unique_id: str | None
    file_name: str | None
    file_size: int | None


def storage_caption(code: str, name: str) -> str:
    """Caption written under files the bot posts into the storage channel."""
    return f"<code>{escape(code)}</code> — {escape(name)}"


def _user_caption(movie: Movie) -> str:
    caption = f"🎬 <b>{escape(movie.movie_name)}</b>"
    if movie.description:
        caption += f"\n\n{escape(movie.description)}"
    return caption if len(caption) <= 1024 else f"🎬 <b>{escape(movie.movie_name)}</b>"


class StorageService:
    def __init__(self, bot: Bot, storage_chat_id: int) -> None:
        self._bot = bot
        self._chat = storage_chat_id

    async def ingest(self, message: Message, caption: str) -> StoredFile:
        """Register an admin-supplied file and return where it lives in storage.

        * Forwarded from the storage channel -> reuse the original message ID.
        * Anything else -> re-post by file_id (no download/upload, works for any size
          and even for forwards with protected content), then store the new message ID.
        """
        media = message.video or message.document
        if media is None:
            raise UnsupportedFileError("Only video or document files are supported")

        info = {
            "file_id": media.file_id,
            "file_unique_id": media.file_unique_id,
            "file_name": getattr(media, "file_name", None),
            "file_size": media.file_size,
        }

        origin = message.forward_origin
        if isinstance(origin, MessageOriginChannel) and origin.chat.id == self._chat:
            return StoredFile(message_id=origin.message_id, copied=False, **info)

        if message.video:
            sent = await self._bot.send_video(
                self._chat, message.video.file_id, caption=caption, supports_streaming=True
            )
        else:
            assert message.document is not None
            sent = await self._bot.send_document(
                self._chat, message.document.file_id, caption=caption
            )
        return StoredFile(message_id=sent.message_id, copied=True, **info)

    async def send_movie(self, user_chat_id: int, movie: Movie) -> None:
        """Copy the stored file to the user (sends the original file, no re-upload)."""
        if movie.file_message_id is None:
            raise FileUnavailableError("Movie has no stored file")

        for attempt in (1, 2):
            try:
                await self._bot.copy_message(
                    chat_id=user_chat_id,
                    from_chat_id=self._chat,
                    message_id=movie.file_message_id,
                    caption=_user_caption(movie),
                )
                return
            except TelegramRetryAfter as exc:
                if attempt == 2:
                    raise
                logger.warning("Flood control, sleeping %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            except TelegramBadRequest as exc:
                if any(marker in str(exc).lower() for marker in _GONE_MARKERS):
                    raise FileUnavailableError(str(exc)) from exc
                raise

    async def delete_stored(self, message_id: int) -> None:
        """Best-effort removal of a message the bot itself created in storage."""
        try:
            await self._bot.delete_message(self._chat, message_id)
        except TelegramAPIError:
            logger.warning("Could not delete storage message %s", message_id)
