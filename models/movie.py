"""Domain model for a movie record."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Movie:
    id: int
    movie_code: str
    movie_name: str
    description: str
    file_message_id: int | None
    online_link: str | None
    added_date: str
    file_id: str | None = None
    file_unique_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Movie":
        return cls(**{f.name: row[f.name] for f in fields(cls)})

    @property
    def has_file(self) -> bool:
        return self.file_message_id is not None

    @property
    def has_link(self) -> bool:
        return bool(self.online_link)
