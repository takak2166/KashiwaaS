"""Platform-neutral mention value objects and duplicate-assistant helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotMention:
    """Normalized mention for Slack / Mattermost (and future platforms)."""

    thread_key: str
    event_key: tuple[str, str]
    raw_text: str
    question: str


def is_duplicate_assistant_reply(
    *,
    last_sent_message_id: str | None,
    last_sent_fingerprint: str | None,
    assistant_message_id: str,
    assistant_text_fingerprint: str,
) -> bool:
    """Whether the assistant message matches the last one we already posted (id or content)."""
    if last_sent_message_id is not None and assistant_message_id == last_sent_message_id:
        return True
    if last_sent_fingerprint is not None and assistant_text_fingerprint == last_sent_fingerprint:
        return True
    return False
