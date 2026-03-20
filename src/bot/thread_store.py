"""
Thread Store Module
Maps Slack thread timestamps to Cursor agent IDs with TTL-based expiration.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24 hours


@dataclass
class _Entry:
    agent_id: str
    last_message_id: Optional[str] = None
    last_message_fingerprint: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class ThreadStore:
    """
    In-memory mapping from Slack thread_ts to Cursor agent_id.

    Entries are automatically evicted after the configured TTL to prevent
    unbounded memory growth. Thread-safe for concurrent access.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._store: Dict[str, _Entry] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, thread_ts: str) -> Optional[str]:
        """Return the agent_id for a thread, or None if missing/expired."""
        with self._lock:
            self._evict_expired()
            entry = self._store.get(thread_ts)
            if entry is None:
                return None
            return entry.agent_id

    def set(self, thread_ts: str, agent_id: str) -> None:
        """Associate a thread with an agent (clears last_message_id/fingerprint)."""
        with self._lock:
            self._store[thread_ts] = _Entry(agent_id=agent_id)
            logger.debug(f"Stored mapping: {thread_ts} -> {agent_id}")

    def get_last_message_id(self, thread_ts: str) -> Optional[str]:
        """Return the last assistant message id for this thread, or None."""
        with self._lock:
            self._evict_expired()
            entry = self._store.get(thread_ts)
            return entry.last_message_id if entry else None

    def set_last_message_id(self, thread_ts: str, message_id: str) -> None:
        """Record the last assistant message id for this thread (for retry detection)."""
        with self._lock:
            entry = self._store.get(thread_ts)
            if entry is not None:
                entry.last_message_id = message_id
                logger.debug(f"Stored last_message_id for {thread_ts} -> {message_id}")

    def get_last_message_fingerprint(self, thread_ts: str) -> Optional[str]:
        """Return the last assistant message fingerprint for this thread, or None."""
        with self._lock:
            self._evict_expired()
            entry = self._store.get(thread_ts)
            return entry.last_message_fingerprint if entry else None

    def set_last_message_fingerprint(self, thread_ts: str, fingerprint: str) -> None:
        """Record the last assistant message fingerprint for this thread (for duplicate content detection)."""
        with self._lock:
            entry = self._store.get(thread_ts)
            if entry is not None:
                entry.last_message_fingerprint = fingerprint
                logger.debug(f"Stored last_message_fingerprint for {thread_ts}")

    def remove(self, thread_ts: str) -> None:
        """Remove a mapping if it exists."""
        with self._lock:
            self._store.pop(thread_ts, None)

    def _evict_expired(self) -> None:
        """Remove entries older than TTL. Must be called under lock."""
        now = time.time()
        expired = [ts for ts, entry in self._store.items() if now - entry.created_at > self._ttl]
        for ts in expired:
            del self._store[ts]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired thread mappings")

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired()
            return len(self._store)
