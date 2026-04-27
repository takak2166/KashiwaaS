"""
Chat mention helpers for Slack ``app_mention`` and Mattermost ``posted`` events (no I/O).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MENTION_PATTERN = re.compile(r"<@[\w]+>")


def mattermost_bot_mention_pattern(bot_user_id: str) -> re.Pattern[str]:
    """Match ``@userid`` style mentions Mattermost sends for the bot user."""
    return re.compile(rf"@({re.escape(bot_user_id)})\b")


def mattermost_bot_mention_strip_patterns(
    bot_user_id: str,
    bot_username: str,
) -> tuple[re.Pattern[str], ...]:
    """Patterns for stripping ``@userid`` and optional ``@username`` from message text."""
    pats: list[re.Pattern[str]] = [mattermost_bot_mention_pattern(bot_user_id)]
    u = (bot_username or "").strip()
    if u and u != bot_user_id:
        pats.append(re.compile(rf"@({re.escape(u)})\b"))
    return tuple(pats)


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


def _coerce_mention_id_list(raw: object) -> list[str] | None:
    """Parse Mattermost mention id lists (native list or JSON-encoded array string)."""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(loaded, list):
            return [str(x) for x in loaded]
    return None


def mattermost_broadcast_mentions_bot(data: dict, bot_user_id: str) -> bool:
    """Whether WebSocket ``posted`` event ``data`` top-level ``mentions`` includes the bot user id."""
    ids = _coerce_mention_id_list(data.get("mentions"))
    return bool(ids and bot_user_id in ids)


def mattermost_is_direct_message_channel(data: dict) -> bool:
    """Whether ``posted`` event ``data`` is a 1:1 DM channel (no ``@userid`` in body, but addressed to the bot)."""
    return str(data.get("channel_type") or "").upper() == "D"


def mattermost_message_has_at_username(message: str, username: str) -> bool:
    """Whether ``message`` contains ``@username`` as a Mattermost-style token (word boundary)."""
    u = username.strip()
    if not u:
        return False
    return re.search(rf"@{re.escape(u)}\b", message) is not None


def mattermost_post_mentions_bot(
    post: dict,
    bot_user_id: str,
    *,
    bot_username: str = "",
) -> bool:
    """Whether the post targets the bot (message token and/or ``props`` mention metadata)."""
    message = str(post.get("message") or "")
    if f"@{bot_user_id}" in message:
        return True
    if mattermost_message_has_at_username(message, bot_username):
        return True
    props = post.get("props")
    if not isinstance(props, dict):
        return False
    mentions_raw = props.get("mentions")
    mentions = _coerce_mention_id_list(mentions_raw)
    if mentions is not None and bot_user_id in mentions:
        return True
    if isinstance(mentions_raw, dict):
        if bot_user_id in mentions_raw:
            return True
        inner = mentions_raw.get("mentions")
        if isinstance(inner, dict) and bot_user_id in inner:
            return True
        if isinstance(inner, list) and bot_user_id in inner:
            return True
    return False


def mattermost_posted_event_from_broadcast(
    data: dict,
    *,
    bot_user_id: str,
    bot_username: str = "",
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
    if (
        not mattermost_post_mentions_bot(post, bot_user_id, bot_username=bot_username)
        and not mattermost_broadcast_mentions_bot(data, bot_user_id)
        and not mattermost_is_direct_message_channel(data)
    ):
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


def extract_question_mattermost(
    text: str,
    bot_user_id: str,
    bot_username: str = "",
) -> str:
    """Remove Mattermost ``@userid`` / ``@username`` bot triggers and normalize whitespace."""
    out = text
    for pat in mattermost_bot_mention_strip_patterns(bot_user_id, bot_username):
        out = pat.sub("", out)
    return out.strip()


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
