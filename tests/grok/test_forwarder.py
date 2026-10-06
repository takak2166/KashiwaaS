"""Tests for HttpGrokForwarder."""

from __future__ import annotations

from http.client import IncompleteRead
from unittest.mock import MagicMock, patch

from src.grok.common.canonical import CanonicalInbound
from src.grok.common.forwarder import HttpGrokForwarder


def _sample_payload() -> CanonicalInbound:
    return CanonicalInbound(
        platform="mattermost",
        channel_id="c1",
        thread_id="t1",
        post_id="p1",
        user="u1",
        text="hi",
    )


@patch("src.grok.common.forwarder.urllib.request.urlopen")
def test_forward_incomplete_read_returns_transport_error(urlopen_mock: MagicMock) -> None:
    resp = MagicMock()
    resp.status = 200
    resp.read.side_effect = IncompleteRead(b"partial", 100)
    urlopen_mock.return_value.__enter__.return_value = resp

    forwarder = HttpGrokForwarder("https://grok.example/hook", "token")
    result = forwarder.forward(_sample_payload())

    assert result.transport_error is True
    assert result.status == 0
    assert result.body == b""
