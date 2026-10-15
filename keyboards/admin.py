"""Inline keyboards for the admin panel."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class EditField(CallbackData, prefix="ef"):
    field: str  # name | description | link | file | close
    code: str


class DeleteConfirm(CallbackData, prefix="del"):
    action: str  # yes | no
    code: str


class ListPage(CallbackData, prefix="lp"):
    page: int


def edit_fields_keyboard(code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, field in (
        ("✏️ Name", "name"),
        ("📝 Description", "description"),
        ("🔗 Online link", "link"),
        ("🎞 Movie file", "file"),
        ("✖️ Close", "close"),
    ):
        builder.button(text=label, callback_data=EditField(field=field, code=code))
    builder.adjust(2)
    return builder.as_markup()


def delete_confirm_keyboard(code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Yes, delete", callback_data=DeleteConfirm(action="yes", code=code))
    builder.button(text="↩️ Cancel", callback_data=DeleteConfirm(action="no", code=code))
    builder.adjust(2)
    return builder.as_markup()


def list_keyboard(page: int, pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(text="⬅️ Prev", callback_data=ListPage(page=page - 1))
    builder.button(text=f"{page}/{pages}", callback_data=ListPage(page=page))
    if page < pages:
        builder.button(text="Next ➡️", callback_data=ListPage(page=page + 1))
    builder.adjust(3)
    return builder.as_markup()
