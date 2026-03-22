"""
Pure helpers for CLI fetch: date windows and dummy Slack payloads.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def resolve_fetch_window(
    end_date: datetime,
    days: int,
    fetch_all: bool,
) -> Tuple[Optional[datetime], datetime]:
    """
    Compute (oldest, latest) for Slack history API.
    When fetch_all is True, oldest is None (API default = channel beginning).
    """
    if fetch_all:
        return None, end_date
    return end_date - timedelta(days=days), end_date


def build_dummy_slack_raw_messages(count: int = 10) -> Tuple[str, List[Dict[str, Any]]]:
    """Synthetic Slack API message dicts for offline testing."""
    channel_name = "dummy-channel"
    base = datetime.now() - timedelta(days=1)
    dummy_messages: List[Dict[str, Any]] = []
    for i in range(count):
        dummy_messages.append(
            {
                "type": "message",
                "user": f"U{i}",
                "username": f"User{i}",
                "text": f"Dummy message {i}",
                "ts": f"{base.timestamp() - (i * 3600):.6f}",
                "client_msg_id": f"dummy-msg-{i}",
                "team": "TH6LHJ38S",
                "reactions": [
                    {"name": "thumbsup", "count": i, "users": [f"U{n}" for n in range(i)]},
                    {"name": "heart", "count": 2, "users": ["U1", "U2"]},
                ],
                "blocks": [
                    {
                        "type": "rich_text",
                        "block_id": f"dummy-block-{i}",
                        "elements": [
                            {"type": "rich_text_section", "elements": [{"type": "text", "text": f"Dummy message {i}"}]}
                        ],
                    }
                ],
            }
        )
    return channel_name, dummy_messages
