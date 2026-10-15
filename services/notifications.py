"""Small helper for alerting admins about operational problems."""
from __future__ import annotations

import logging
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, admin_ids: Iterable[int], text: str) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError:
            logger.warning("Could not notify admin %s", admin_id)
