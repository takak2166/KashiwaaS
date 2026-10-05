"""Validate ``GROK_TARGET_URL`` at process startup."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _allow_insecure_http() -> bool:
    raw = os.environ.get("GROK_ALLOW_INSECURE_HTTP", "").strip().lower()
    return raw in _TRUTHY


def validate_grok_target_url(url: str, log: logging.Logger | None = None) -> str:
    """Return ``url`` when scheme policy is satisfied; otherwise raise ``SystemExit``."""
    value = url.strip()
    if not value:
        raise SystemExit("Missing required env: GROK_TARGET_URL")

    parsed = urlparse(value)
    if not parsed.hostname:
        raise SystemExit("GROK_TARGET_URL must include a hostname (e.g. https://grok.example/hook)")

    scheme = (parsed.scheme or "").lower()
    if scheme == "https":
        return value
    if scheme == "http":
        if not _allow_insecure_http():
            raise SystemExit(
                "GROK_TARGET_URL uses http; set GROK_ALLOW_INSECURE_HTTP=1 to opt in "
                "(Bearer token will be sent in cleartext)"
            )
        if log is not None:
            log.warning(
                "GROK_TARGET_URL uses http with GROK_ALLOW_INSECURE_HTTP; Bearer token will be sent in cleartext"
            )
        return value

    raise SystemExit(f"GROK_TARGET_URL scheme must be http or https (got {parsed.scheme!r})")


def grok_target_url_from_env(log: logging.Logger | None = None) -> str:
    return validate_grok_target_url(os.environ.get("GROK_TARGET_URL", ""), log)
