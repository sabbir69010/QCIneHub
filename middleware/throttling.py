"""Per-user rate limiting (in-memory; swap for Redis if you run several instances)."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or self._interval <= 0:
            return await handler(event, data)

        now = time.monotonic()
        if now - self._last_seen.get(user.id, 0.0) < self._interval:
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Please slow down.")
            return None

        self._last_seen[user.id] = now
        if len(self._last_seen) > 10_000:  # keep memory bounded
            cutoff = now - 60
            self._last_seen = {u: t for u, t in self._last_seen.items() if t > cutoff}
        return await handler(event, data)
