"""Canonical JSON payload for Grok webhook inbound."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CanonicalInbound:
    platform: str
    channel_id: str
    thread_id: str
    post_id: str
    user: str
    text: str
    trigger_id: str | None = None
    team_id: str | None = None
    event_id: str | None = None
    client_msg_id: str | None = None
    received_at: str | None = None

    def to_grok_json(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None and v != ""}
