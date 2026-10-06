"""Hold Grok reply text until Slack thread post succeeds (forward already done)."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from src.grok.slack_inbound.reply import SlackThreadTarget


@dataclass(frozen=True)
class PendingSlackReply:
    target: SlackThreadTarget
    text: str


class PendingSlackReplyStore:
    """In-memory pending replies keyed by inbound dedup key."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingSlackReply] = {}
        self._lock = Lock()

    def put(self, dedup_key: str, pending: PendingSlackReply) -> None:
        with self._lock:
            self._pending[dedup_key] = pending

    def get(self, dedup_key: str) -> PendingSlackReply | None:
        with self._lock:
            return self._pending.get(dedup_key)

    def forget(self, dedup_key: str) -> None:
        with self._lock:
            self._pending.pop(dedup_key, None)
