"""Parse Mattermost outgoing webhook bodies (JSON or form-urlencoded)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs

from src.bot.adapters.mattermost.mention_parser import extract_question_mattermost
from src.grok.common.canonical import CanonicalInbound


def parse_mm_payload(raw: bytes, content_type: str | None) -> dict[str, Any]:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    text = raw.decode("utf-8", errors="replace")
    if ct == "application/json":
        loaded = json.loads(text or "{}")
        if not isinstance(loaded, dict):
            raise ValueError("json body must be an object")
        return loaded
    if ct == "application/x-www-form-urlencoded" or "=" in text and not text.lstrip().startswith("{"):
        pairs = parse_qs(text, keep_blank_values=True)
        flat: dict[str, Any] = {k: (v[0] if len(v) == 1 else v) for k, v in pairs.items()}
        return flat
    # Default: try JSON, else form
    try:
        loaded = json.loads(text or "{}")
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass
    pairs = parse_qs(text, keep_blank_values=True)
    return {k: (v[0] if len(v) == 1 else v) for k, v in pairs.items()}


def strip_bot_mentions(
    text: str,
    *,
    bot_user_id: str = "",
    bot_username: str = "",
    trigger_word: str = "",
) -> str:
    """Strip bot/trigger tokens only; keep other ``@user`` mentions (see ``mention_parser``)."""
    uid = (bot_user_id or "").strip()
    uname = (bot_username or "").strip()
    out = text or ""
    if uid or uname:
        effective_uid = uid or uname
        out = extract_question_mattermost(out, effective_uid, bot_username=uname)
    tw = (trigger_word or "").strip()
    if tw:
        out = re.sub(rf"^\s*(?:@)?{re.escape(tw)}\b", "", out)
    return out.strip()


def mattermost_thread_id(payload: dict[str, Any]) -> str:
    """Thread key: ``root_id`` when present, else the post's own ``post_id``/``id`` (payload only, no API fetch)."""
    root_id = str(payload.get("root_id") or "").strip()
    post_id = str(payload.get("post_id") or payload.get("id") or "").strip()
    return root_id or post_id


def to_canonical(
    payload: dict[str, Any],
    *,
    received_at: str | None = None,
    bot_user_id: str = "",
    bot_username: str = "",
    default_trigger_word: str = "",
) -> CanonicalInbound:
    channel_id = str(payload.get("channel_id") or "")
    post_id = str(payload.get("post_id") or payload.get("id") or "")
    user = str(payload.get("user_name") or payload.get("user_id") or payload.get("user") or "")
    trigger_word = str(payload.get("trigger_word") or default_trigger_word or "")
    text = strip_bot_mentions(
        str(payload.get("text") or ""),
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        trigger_word=trigger_word,
    )
    trigger_id = str(payload.get("trigger_id") or "") or None
    return CanonicalInbound(
        platform="mattermost",
        channel_id=channel_id,
        thread_id=mattermost_thread_id(payload),
        post_id=post_id,
        user=user,
        text=text,
        trigger_id=trigger_id,
        received_at=received_at,
    )
