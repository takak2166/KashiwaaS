"""Content-Length parsing for inbound HTTP handlers."""

from __future__ import annotations


def parse_content_length(value: str | None) -> int | None:
    """Return body length in bytes, or ``None`` if the header is invalid or negative."""
    if value is None:
        return 0
    stripped = value.strip()
    if not stripped:
        return 0
    try:
        length = int(stripped)
    except ValueError:
        return None
    if length < 0:
        return None
    return length
