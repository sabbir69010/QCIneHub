"""Custom exceptions shared across layers."""
from __future__ import annotations


class DatabaseUnavailableError(Exception):
    """The database could not be opened, read or written."""


class DuplicateMovieCodeError(Exception):
    """A movie with this code already exists."""

    def __init__(self, code: str) -> None:
        super().__init__(f"Movie code already exists: {code}")
        self.code = code


class FileUnavailableError(Exception):
    """The stored movie file is missing from the storage channel."""


class UnsupportedFileError(Exception):
    """The admin sent something that is not a video or document."""
