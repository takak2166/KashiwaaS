"""
Thread Store Module
Maps Slack thread timestamps to Cursor agent IDs in Valkey (Redis protocol) with sliding TTL.
"""

from __future__ import annotations

from typing import Any, Optional

from valkey import Valkey

from src.utils.config import ValkeyConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

_F_AGENT_ID = "agent_id"
_F_LAST_MESSAGE_ID = "last_message_id"
_F_LAST_FINGERPRINT = "last_message_fingerprint"


class ThreadStore:
    """
    Valkey Hash per Slack thread_ts: agent_id and optional last assistant message metadata.

    Keys use a sliding TTL (refresh on read/write) so idle threads expire.
    """

    _KEY_PREFIX = "kashiwaas:thread:"

    def __init__(self, cfg: ValkeyConfig, *, client: Any | None = None):
        self._ttl = cfg.thread_ttl_seconds
        self._client: Any = client if client is not None else Valkey.from_url(cfg.url, decode_responses=True)

    def _key(self, thread_ts: str) -> str:
        return f"{self._KEY_PREFIX}{thread_ts}"

    def _refresh_ttl(self, key: str) -> None:
        if self._ttl > 0:
            self._client.expire(key, self._ttl)

    def get(self, thread_ts: str) -> Optional[str]:
        """Return the agent_id for a thread, or None if missing/expired."""
        key = self._key(thread_ts)
        agent_id = self._client.hget(key, _F_AGENT_ID)
        if agent_id is not None:
            self._refresh_ttl(key)
        return agent_id

    def set(self, thread_ts: str, agent_id: str) -> None:
        """Associate a thread with an agent (clears last_message_id/fingerprint)."""
        key = self._key(thread_ts)
        pipe = self._client.pipeline()
        pipe.hset(key, mapping={_F_AGENT_ID: agent_id})
        pipe.hdel(key, _F_LAST_MESSAGE_ID, _F_LAST_FINGERPRINT)
        pipe.execute()
        self._refresh_ttl(key)
        logger.debug(f"Stored mapping: {thread_ts} -> {agent_id}")

    def get_last_message_id(self, thread_ts: str) -> Optional[str]:
        """Return the last assistant message id for this thread, or None."""
        key = self._key(thread_ts)
        if not self._client.exists(key):
            return None
        self._refresh_ttl(key)
        return self._client.hget(key, _F_LAST_MESSAGE_ID)

    def set_last_message_id(self, thread_ts: str, message_id: str) -> None:
        """Record the last assistant message id for this thread (for retry detection)."""
        key = self._key(thread_ts)
        if not self._client.exists(key):
            return
        self._client.hset(key, _F_LAST_MESSAGE_ID, message_id)
        self._refresh_ttl(key)
        logger.debug(f"Stored last_message_id for {thread_ts} -> {message_id}")

    def get_last_message_fingerprint(self, thread_ts: str) -> Optional[str]:
        """Return the last assistant message fingerprint for this thread, or None."""
        key = self._key(thread_ts)
        if not self._client.exists(key):
            return None
        self._refresh_ttl(key)
        return self._client.hget(key, _F_LAST_FINGERPRINT)

    def set_last_message_fingerprint(self, thread_ts: str, fingerprint: str) -> None:
        """Record the last assistant message fingerprint for duplicate content detection."""
        key = self._key(thread_ts)
        if not self._client.exists(key):
            return
        self._client.hset(key, _F_LAST_FINGERPRINT, fingerprint)
        self._refresh_ttl(key)
        logger.debug(f"Stored last_message_fingerprint for {thread_ts}")

    def remove(self, thread_ts: str) -> None:
        """Remove a mapping if it exists."""
        self._client.delete(self._key(thread_ts))

    def __len__(self) -> int:
        pattern = f"{self._KEY_PREFIX}*"
        return sum(1 for _ in self._client.scan_iter(match=pattern, count=100))
