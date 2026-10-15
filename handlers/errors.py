"""Global error handler: friendly messages for users, full detail in the logs."""
from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import ErrorEvent

from services.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception

    if isinstance(exc, TelegramForbiddenError):
        logger.info("User blocked the bot or chat is unavailable")
        return True
    if isinstance(exc, DatabaseUnavailableError):
        logger.error("Database unavailable while handling update: %s", exc)
        text = "⚠️ Our database is temporarily unavailable. Please try again in a moment."
    else:
        logger.exception("Unhandled error", exc_info=exc)
        text = "⚠️ Something went wrong. Please try again later."

    update = event.update
    try:
        if update.message:
            await update.message.answer(text)
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
    except TelegramAPIError:
        logger.warning("Could not deliver the error message to the user")
    return True
