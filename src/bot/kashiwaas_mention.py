"""
Pure helpers for Slack app_mention handling (no I/O).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MENTION_PATTERN = re.compile(r"<@[\w]+>")


@dataclass(frozen=True)
class SlackMentionEvent:
    """Normalized fields from a Slack ``app_mention`` payload."""

    channel: str
    event_ts: str
    thread_ts: str
    raw_text: str


def slack_mention_event_from_dict(event: dict) -> SlackMentionEvent:
    """Extract stable fields from Bolt ``event`` dict."""
    event_ts = event.get("ts", "")
    return SlackMentionEvent(
        channel=event.get("channel", ""),
        event_ts=event_ts,
        thread_ts=event.get("thread_ts") or event_ts,
        raw_text=event.get("text", ""),
    )


def extract_question(text: str) -> str:
    """Remove mention tags and extract the user question text."""
    return MENTION_PATTERN.sub("", text).strip()


def is_duplicate_assistant_reply(
    *,
    last_sent_message_id: str | None,
    last_sent_fingerprint: str | None,
    assistant_message_id: str,
    assistant_text_fingerprint: str,
) -> bool:
    """Whether the assistant message matches the last one we already posted (id or content)."""
    if last_sent_message_id and assistant_message_id == last_sent_message_id:
        return True
    if last_sent_fingerprint and assistant_text_fingerprint == last_sent_fingerprint:
        return True
    return False
