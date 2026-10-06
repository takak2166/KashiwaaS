"""Bounded HTTP request body reads with socket read timeout."""

from __future__ import annotations

import socket
from typing import IO

# Slow clients must not hold the single-thread HTTPServer on rfile.read().
# Grok forward uses a separate urllib timeout (default 60s); this applies only to inbound body read.
DEFAULT_REQUEST_BODY_READ_TIMEOUT_SECONDS = 30.0


class RequestBodyReadTimeoutError(TimeoutError):
    """Inbound body was not fully received within the read timeout."""


def read_request_body(
    rfile: IO[bytes],
    connection: socket.socket,
    length: int,
    timeout_seconds: float = DEFAULT_REQUEST_BODY_READ_TIMEOUT_SECONDS,
) -> bytes:
    """Read exactly ``length`` bytes from ``rfile`` with a per-read socket timeout."""
    connection.settimeout(timeout_seconds)
    try:
        raw = rfile.read(length)
    except TimeoutError:
        raise RequestBodyReadTimeoutError from None
    finally:
        connection.settimeout(None)

    if len(raw) != length:
        raise RequestBodyReadTimeoutError
    return raw
