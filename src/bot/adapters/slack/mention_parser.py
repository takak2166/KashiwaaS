"""Parse Slack ``app_mention`` payloads into domain ``BotMention`` (no I/O)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.bot.domain.mention import BotMention

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


def bot_mention_from_slack_event(event: dict) -> BotMention:
    """Build a platform-neutral ``BotMention`` from a Slack ``app_mention`` event dict."""
    ev = slack_mention_event_from_dict(event)
    return BotMention(
        thread_key=ev.thread_ts,
        event_key=(ev.channel, ev.event_ts),
        raw_text=ev.raw_text,
        question=extract_question(ev.raw_text),
    )
