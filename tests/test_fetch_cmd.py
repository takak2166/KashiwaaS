"""Tests for fetch command (lazy Slack iterator + alerts)."""

from datetime import datetime
from unittest.mock import patch

import pytest

from src.cli.fetch_cmd import _slack_fetch_iter_with_alert


def _failing_slack_iter():
    raise RuntimeError("slack api failed")
    yield  # pragma: no cover


@patch("src.cli.fetch_cmd.alert")
def test_slack_fetch_iter_with_alert_on_lazy_iteration(mock_alert) -> None:
    """Generator bodies run on iteration; wrapper must catch and alert."""
    end = datetime(2025, 1, 2, 12, 0, 0)
    it = _slack_fetch_iter_with_alert(
        _failing_slack_iter(),
        channel_name="test-ch",
        start_date=None,
        end_date=end,
    )
    with pytest.raises(RuntimeError, match="slack api failed"):
        list(it)
    mock_alert.assert_called_once()
    call_kw = mock_alert.call_args[1]
    assert call_kw["title"] == "Message Fetch Error"
    assert call_kw["details"]["channel"] == "test-ch"
