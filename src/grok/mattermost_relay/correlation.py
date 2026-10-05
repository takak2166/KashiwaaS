"""Server-side in-flight correlation for Mattermost replies."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class MattermostRoutingContext:
    channel_id: str
    thread_id: str
    post_id: str


class MattermostCorrelationStore:
    """Maps trigger ``post_id`` → routing context for Bot PAT replies (fail-closed if missing)."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._by_post: dict[str, tuple[MattermostRoutingContext, float]] = {}
        self._lock = Lock()

    def put(self, ctx: MattermostRoutingContext) -> None:
        now = time.time()
        with self._lock:
            self._evict(now)
            self._by_post[ctx.post_id] = (ctx, now)

    def get(self, post_id: str) -> MattermostRoutingContext | None:
        now = time.time()
        with self._lock:
            self._evict(now)
            entry = self._by_post.get(post_id)
            if entry is None:
                return None
            return entry[0]

    def _evict(self, now: float) -> None:
        expired = [k for k, (_, t) in self._by_post.items() if now - t > self._ttl]
        for k in expired:
            del self._by_post[k]


class OutboundReplyIdempotency:
    """At most one visible outbound reply per idempotency key (e.g. Slack team:event)."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = Lock()

    def _evict(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > self._ttl]
        for k in expired:
            del self._seen[k]

    def mark_if_absent(self, key: str) -> bool:
        """Reserve ``key`` under one lock; return True if this caller owns the reply slot."""
        now = time.time()
        with self._lock:
            self._evict(now)
            if key in self._seen:
                return False
            self._seen[key] = now
            return True

    def forget(self, key: str) -> None:
        with self._lock:
            self._seen.pop(key, None)
