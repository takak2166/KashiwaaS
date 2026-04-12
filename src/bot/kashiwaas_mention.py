"""
Pure helpers for Slack app_mention handling (no I/O).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MENTION_PATTERN = re.compile(r"<@[\w]+>")


def mattermost_bot_mention_pattern(bot_user_id: str) -> re.Pattern[str]:
    """Match ``@userid`` style mentions Mattermost sends for the bot user."""
    return re.compile(rf"@({re.escape(bot_user_id)})\b")


@dataclass(frozen=True)
class SlackMentionEvent:
    """Normalized fields from a Slack ``app_mention`` payload."""

    channel: str
    event_ts: str
    thread_ts: str
    raw_text: str


@dataclass(frozen=True)
class MattermostPostedEvent:
    """Normalized fields from a Mattermost ``posted`` WebSocket event."""

    channel_id: str
    root_post_id: str
    event_post_id: str
    raw_text: str


def mattermost_root_post_id(post: dict) -> str:
    """Thread root id for Valkey / Cursor context (top-level post id for new threads)."""
    root = post.get("root_id") or ""
    if root:
        return root
    pid = post.get("id") or ""
    return str(pid)


def mattermost_post_mentions_bot(post: dict, bot_user_id: str) -> bool:
    """Whether the post targets the bot (message token and/or ``props`` mention metadata)."""
    message = str(post.get("message") or "")
    if f"@{bot_user_id}" in message:
        return True
    props = post.get("props")
    if not isinstance(props, dict):
        return False
    mentions = props.get("mentions")
    if isinstance(mentions, list) and bot_user_id in mentions:
        return True
    if isinstance(mentions, dict):
        if bot_user_id in mentions:
            return True
        inner = mentions.get("mentions")
        if isinstance(inner, dict) and bot_user_id in inner:
            return True
        if isinstance(inner, list) and bot_user_id in inner:
            return True
    return False


def mattermost_posted_event_from_broadcast(
    data: dict,
    *,
    bot_user_id: str,
) -> MattermostPostedEvent | None:
    """
    Parse ``posted`` event ``data`` (decoded JSON object).

    Returns None if the post does not mention the bot or is from the bot itself.
    """
    post_raw = data.get("post")
    post: dict
    if isinstance(post_raw, dict):
        post = post_raw
    elif isinstance(post_raw, str):
        try:
            loaded = json.loads(post_raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(loaded, dict):
            return None
        post = loaded
    else:
        return None
    channel_id = str(post.get("channel_id") or "")
    post_id = str(post.get("id") or "")
    message = str(post.get("message") or "")
    user_id = str(post.get("user_id") or "")
    if user_id == bot_user_id:
        return None
    if not mattermost_post_mentions_bot(post, bot_user_id):
        return None
    root_post_id = mattermost_root_post_id(post)
    if not channel_id or not post_id or not root_post_id:
        return None
    return MattermostPostedEvent(
        channel_id=channel_id,
        root_post_id=root_post_id,
        event_post_id=post_id,
        raw_text=message,
    )


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


def extract_question_mattermost(text: str, bot_user_id: str) -> str:
    """Remove Mattermost ``@userid`` bot mentions and normalize whitespace."""
    return mattermost_bot_mention_pattern(bot_user_id).sub("", text).strip()


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
