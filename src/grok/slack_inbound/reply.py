"""Post thread replies as the @kashiwaas Slack app."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.grok.mattermost_relay.correlation import OutboundBeginResult, OutboundReplyIdempotency

LOG = logging.getLogger("slack-grok-inbound")


def outbound_reply_key(target: SlackThreadTarget) -> str:
    return f"{target.team_id}:{target.event_id or target.thread_ts}"


@dataclass(frozen=True)
class SlackThreadTarget:
    team_id: str
    channel_id: str
    thread_ts: str
    event_id: str


class SlackReplier(Protocol):
    def post_thread_reply(self, target: SlackThreadTarget, text: str) -> bool: ...

    def outbound_reply_completed(self, target: SlackThreadTarget) -> bool: ...


class SlackWebReplier:
    def __init__(self, bot_token: str, outbound_idempotency: OutboundReplyIdempotency) -> None:
        self._client = WebClient(token=bot_token)
        self._outbound = outbound_idempotency

    def outbound_reply_completed(self, target: SlackThreadTarget) -> bool:
        return self._outbound.is_completed(outbound_reply_key(target))

    def post_thread_reply(self, target: SlackThreadTarget, text: str) -> bool:
        # Outbound reply idempotency (key below) is separate from inbound dedup / pending_replies,
        # which use slack_dedup_key (envelope event_id preferred, else event fields + channel:ts).
        key = outbound_reply_key(target)
        if self._outbound.begin_outbound(key) is not OutboundBeginResult.SEND:
            return False
        try:
            self._client.chat_postMessage(
                channel=target.channel_id,
                text=text,
                thread_ts=target.thread_ts,
            )
        except SlackApiError as e:
            LOG.warning("slack post failed status=%s", getattr(e.response, "status_code", "unknown"))
            self._outbound.forget(key)
            return False
        except Exception:
            LOG.exception("slack post failed")
            self._outbound.forget(key)
            return False
        self._outbound.mark_completed(key)
        return True
