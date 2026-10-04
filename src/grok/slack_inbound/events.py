"""Slack Events API payload helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from src.grok.common.canonical import CanonicalInbound

MENTION_PATTERN = re.compile(r"<@[\w]+>")


def parse_slack_envelope(raw: bytes) -> dict[str, Any]:
    loaded = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(loaded, dict):
        raise ValueError("slack envelope must be object")
    return loaded


def slack_dedup_key(team_id: str, event: dict[str, Any], *, envelope_event_id: str | None = None) -> str:
    event_id = str(envelope_event_id or event.get("event_id") or event.get("client_msg_id") or "")
    if event_id:
        return f"{team_id}:{event_id}"
    channel = str(event.get("channel") or "")
    ts = str(event.get("ts") or "")
    return f"{team_id}:{channel}:{ts}"


def strip_slack_mentions(text: str) -> str:
    return MENTION_PATTERN.sub("", text or "").strip()


def event_to_canonical(
    team_id: str,
    event: dict[str, Any],
    *,
    envelope_event_id: str | None = None,
    received_at: str | None = None,
) -> CanonicalInbound:
    channel_id = str(event.get("channel") or "")
    post_id = str(event.get("ts") or "")
    thread_id = str(event.get("thread_ts") or post_id)
    user = str(event.get("user") or "")
    text = strip_slack_mentions(str(event.get("text") or ""))
    return CanonicalInbound(
        platform="slack",
        channel_id=channel_id,
        thread_id=thread_id,
        post_id=post_id,
        user=user,
        text=text,
        team_id=team_id,
        event_id=str(envelope_event_id or event.get("event_id") or "") or None,
        client_msg_id=str(event.get("client_msg_id") or "") or None,
        received_at=received_at,
    )
