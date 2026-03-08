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
        """Associate a thread with an agent."""
        with self._lock:
            self._store[thread_ts] = _Entry(agent_id=agent_id)
            logger.debug(f"Stored mapping: {thread_ts} -> {agent_id}")

    def remove(self, thread_ts: str) -> None:
        """Remove a mapping if it exists."""
        with self._lock:
            self._store.pop(thread_ts, None)

    def _evict_expired(self) -> None:
        """Remove entries older than TTL. Must be called under lock."""
        now = time.time()
        expired = [
            ts for ts, entry in self._store.items()
            if now - entry.created_at > self._ttl
        ]
        for ts in expired:
            del self._store[ts]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired thread mappings")

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired()
            return len(self._store)
