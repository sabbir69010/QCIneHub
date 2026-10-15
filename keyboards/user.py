"""Inline keyboards shown to regular users."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class MovieAction(CallbackData, prefix="mv"):
    """Callback payload. Only the code travels; the DB is re-queried on click."""

    action: str  # "watch" | "dl"
    code: str


def movie_actions_keyboard(code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Watch Online", callback_data=MovieAction(action="watch", code=code))
    builder.button(text="📥 Download Movie", callback_data=MovieAction(action="dl", code=code))
    builder.adjust(1)
    return builder.as_markup()


def watch_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎥 Watch Online", url=url)]]
    )
