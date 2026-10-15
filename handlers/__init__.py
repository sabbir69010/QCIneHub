"""Router assembly."""
from __future__ import annotations

from aiogram import Router

from config import Settings
from handlers import admin, user
from middleware.admin import AdminOnlyMiddleware


def build_root_router(settings: Settings) -> Router:
    root = Router(name="root")

    guard = AdminOnlyMiddleware(settings.admin_ids)
    admin.router.message.middleware(guard)
    admin.router.callback_query.middleware(guard)

    # Order matters: admin first so its FSM states/commands take priority.
    root.include_routers(admin.router, user.router)
    return root
