"""Blocks every admin-router handler for non-admin users."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class AdminOnlyMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: frozenset[int]) -> None:
        self._admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id not in self._admin_ids:
            logger.warning(
                "Unauthorized admin access attempt: user_id=%s username=%s",
                getattr(user, "id", None),
                getattr(user, "username", None),
            )
            if isinstance(event, Message):
                await event.answer("⛔ You are not authorized to use this command.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Not authorized.", show_alert=True)
            return None
        return await handler(event, data)
