"""Input validation and normalisation. Pure functions, easy to unit-test."""
from __future__ import annotations

import re
from urllib.parse import urlparse

CODE_PATTERN = re.compile(r"[A-Z0-9_-]{3,20}")
MAX_NAME_LEN = 100
MAX_DESCRIPTION_LEN = 600
MAX_URL_LEN = 1024

CODE_RULES = (
    "⚠️ Invalid code. Use 3–20 characters: letters, numbers, <code>-</code> or "
    "<code>_</code> (example: <code>QC1234</code>)."
)


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def is_valid_code(code: str) -> bool:
    return CODE_PATTERN.fullmatch(code) is not None


def clean_name(raw: str) -> str | None:
    name = " ".join(raw.split())
    return name if 1 <= len(name) <= MAX_NAME_LEN else None


def clean_description(raw: str) -> str | None:
    """'-' means empty. Returns None when invalid (too long)."""
    text = raw.strip()
    if text == "-":
        return ""
    return text if len(text) <= MAX_DESCRIPTION_LEN else None


def clean_url(raw: str) -> str | None:
    """Accept only well-formed http(s) URLs (Telegram rejects anything else on buttons)."""
    url = raw.strip()
    if not url or len(url) > MAX_URL_LEN or any(ch.isspace() for ch in url):
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return url
