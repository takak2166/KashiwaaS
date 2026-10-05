"""Post thread replies as the @kashiwaas Slack app."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.grok.mattermost_relay.correlation import OutboundReplyIdempotency

LOG = logging.getLogger("slack-grok-inbound")


@dataclass(frozen=True)
class SlackThreadTarget:
    team_id: str
    channel_id: str
    thread_ts: str
    event_id: str


class SlackReplier(Protocol):
    def post_thread_reply(self, target: SlackThreadTarget, text: str) -> bool: ...


class SlackWebReplier:
    def __init__(self, bot_token: str, outbound_idempotency: OutboundReplyIdempotency) -> None:
        self._client = WebClient(token=bot_token)
        self._outbound = outbound_idempotency

    def post_thread_reply(self, target: SlackThreadTarget, text: str) -> bool:
        key = f"{target.team_id}:{target.event_id or target.thread_ts}"
        if self._outbound.already_replied(key):
            return False
        try:
            self._client.chat_postMessage(
                channel=target.channel_id,
                text=text,
                thread_ts=target.thread_ts,
            )
        except SlackApiError as e:
            LOG.warning("slack post failed status=%s", getattr(e.response, "status_code", "unknown"))
            return False
        self._outbound.mark_replied(key)
        return True
