"""Tests for inbound HTTP body read timeouts."""

from __future__ import annotations

import io
import socket
import time
from unittest.mock import MagicMock

import pytest

from src.grok.common.request_body import RequestBodyReadTimeoutError, read_request_body


def test_read_request_body_success() -> None:
    conn = MagicMock(spec=socket.socket)
    data = b"x" * 10
    raw = read_request_body(io.BytesIO(data), conn, 10, timeout_seconds=1.0)
    assert raw == data
    assert conn.settimeout.call_args_list[0][0][0] == 1.0
    assert conn.settimeout.call_args_list[-1][0][0] is None


def test_read_request_body_partial_raises() -> None:
    conn = MagicMock(spec=socket.socket)
    with pytest.raises(RequestBodyReadTimeoutError):
        read_request_body(io.BytesIO(b"short"), conn, 100, timeout_seconds=1.0)


def test_read_request_body_socket_timeout() -> None:
    conn = MagicMock(spec=socket.socket)

    class SlowReader(io.BytesIO):
        def read(self, n: int = -1) -> bytes:
            time.sleep(0.05)
            raise TimeoutError

    with pytest.raises(RequestBodyReadTimeoutError):
        read_request_body(SlowReader(b"data"), conn, 4, timeout_seconds=0.01)
