"""Movie CRUD operations. The only module that talks SQL."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

import aiosqlite

from database import Database
from models.movie import Movie
from services.exceptions import DatabaseUnavailableError, DuplicateMovieCodeError

logger = logging.getLogger(__name__)

# Columns that may be changed through update(); guards the dynamic SET clause.
_EDITABLE = frozenset(
    {
        "movie_name", "description", "online_link", "file_message_id",
        "file_id", "file_unique_id", "file_name", "file_size",
    }
)


class MovieService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._write_lock = asyncio.Lock()  # one writer at a time on the shared connection

    # ----------------------------------------------------------- helpers
    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        try:
            async with self._db.conn.execute(sql, params) as cur:
                return await cur.fetchone()
        except aiosqlite.Error as exc:
            logger.exception("Database read failed")
            raise DatabaseUnavailableError("read failed") from exc

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        try:
            async with self._db.conn.execute(sql, params) as cur:
                return list(await cur.fetchall())
        except aiosqlite.Error as exc:
            logger.exception("Database read failed")
            raise DatabaseUnavailableError("read failed") from exc

    async def _write(self, sql: str, params: Sequence[Any]) -> int:
        """Run one write statement in its own transaction; returns rowcount."""
        conn = self._db.conn
        async with self._write_lock:
            try:
                cur = await conn.execute(sql, params)
                await conn.commit()
                return cur.rowcount
            except aiosqlite.IntegrityError:
                await conn.rollback()
                raise
            except aiosqlite.Error as exc:
                await conn.rollback()
                logger.exception("Database write failed")
                raise DatabaseUnavailableError("write failed") from exc

    # -------------------------------------------------------------- read
    async def get_by_code(self, code: str) -> Movie | None:
        row = await self._fetchone("SELECT * FROM movies WHERE movie_code = ?", (code,))
        return Movie.from_row(row) if row else None

    async def count(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS n FROM movies")
        return int(row["n"]) if row else 0

    async def list_page(self, offset: int, limit: int) -> list[Movie]:
        rows = await self._fetchall(
            "SELECT * FROM movies ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [Movie.from_row(r) for r in rows]

    # ------------------------------------------------------------- write
    async def create(
        self,
        *,
        movie_code: str,
        movie_name: str,
        description: str,
        online_link: str | None,
        file_message_id: int,
        file_id: str | None,
        file_unique_id: str | None,
        file_name: str | None,
        file_size: int | None,
    ) -> Movie:
        try:
            await self._write(
                "INSERT INTO movies (movie_code, movie_name, description, online_link, "
                "file_message_id, file_id, file_unique_id, file_name, file_size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (movie_code, movie_name, description, online_link,
                 file_message_id, file_id, file_unique_id, file_name, file_size),
            )
        except aiosqlite.IntegrityError as exc:
            raise DuplicateMovieCodeError(movie_code) from exc
        movie = await self.get_by_code(movie_code)
        if movie is None:  # pragma: no cover - would indicate DB corruption
            raise DatabaseUnavailableError("inserted row not found")
        logger.info("Movie created: %s", movie_code)
        return movie

    async def update(self, code: str, **fields: Any) -> bool:
        """Update whitelisted columns. Returns False if the movie does not exist."""
        if not fields:
            return False
        unknown = set(fields) - _EDITABLE
        if unknown:
            raise ValueError(f"Non-editable columns: {sorted(unknown)}")
        assignments = ", ".join(f"{col} = ?" for col in fields)  # keys are whitelisted
        rowcount = await self._write(
            f"UPDATE movies SET {assignments} WHERE movie_code = ?",
            (*fields.values(), code),
        )
        if rowcount:
            logger.info("Movie updated: %s (%s)", code, ", ".join(fields))
        return rowcount > 0

    async def delete(self, code: str) -> bool:
        rowcount = await self._write("DELETE FROM movies WHERE movie_code = ?", (code,))
        if rowcount:
            logger.info("Movie deleted: %s", code)
        return rowcount > 0
