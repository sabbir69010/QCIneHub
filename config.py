"""Application configuration, loaded once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or malformed."""


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _parse_int(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids = {_parse_int("ADMIN_IDS", p.strip()) for p in raw.split(",") if p.strip()}
    if not ids:
        raise ConfigError("ADMIN_IDS must contain at least one Telegram user ID")
    return frozenset(ids)


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings. The token is excluded from repr() on purpose."""

    bot_token: str = field(repr=False)
    admin_ids: frozenset[int]
    storage_chat_id: int
    db_path: Path
    log_dir: Path
    log_level: str
    throttle_seconds: float


def load_settings() -> Settings:
    try:
        throttle = float(os.getenv("THROTTLE_SECONDS", "0.7"))
    except ValueError as exc:
        raise ConfigError("THROTTLE_SECONDS must be a number") from exc

    return Settings(
        bot_token=_require("BOT_TOKEN"),
        admin_ids=_parse_admin_ids(_require("ADMIN_IDS")),
        storage_chat_id=_parse_int("STORAGE_CHAT_ID", _require("STORAGE_CHAT_ID")),
        db_path=_resolve(os.getenv("DB_PATH", "data/qcine.db")),
        log_dir=_resolve(os.getenv("LOG_DIR", "logs")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        throttle_seconds=throttle,
    )
