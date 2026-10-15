"""SQLite connection management and schema bootstrap."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import aiosqlite

from services.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS movies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_code      TEXT    NOT NULL UNIQUE
                            CHECK (length(movie_code) BETWEEN 3 AND 20),
    movie_name      TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    file_message_id INTEGER,
    online_link     TEXT,
    added_date      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    file_id         TEXT,
    file_unique_id  TEXT,
    file_name       TEXT,
    file_size       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_movies_added_date ON movies (added_date);
"""


class Database:
    """Owns a single shared aiosqlite connection."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseUnavailableError("Database is not connected")
        return self._conn

    async def connect(self) -> None:
        conn: aiosqlite.Connection | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(self._path)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.executescript(SCHEMA_SQL)
            await conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            await conn.commit()
        except (aiosqlite.Error, OSError) as exc:
            if conn is not None:
                await conn.close()
            raise DatabaseUnavailableError(
                f"Cannot open database at {self._path}: {exc}"
            ) from exc

        self._conn = conn
        try:
            os.chmod(self._path, 0o600)  # owner-only: the DB holds your catalogue
        except OSError:
            logger.warning("Could not restrict permissions on %s", self._path)
        logger.info("Database ready at %s", self._path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("Database connection closed")
