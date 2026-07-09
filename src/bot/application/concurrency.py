"""Process-local concurrency helpers for chat bot handlers."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class _LockEntry:
    lock: threading.Lock
    last_used_at: float = field(default_factory=time.time)


class ThreadLockRegistry:
    """Serialize work per logical thread key within one Python process."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._locks: dict[str, _LockEntry] = {}
        self._guard = threading.Lock()

    def _evict_unlocked(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._locks.items()
            if now - entry.last_used_at > self._ttl_seconds and not entry.lock.locked()
        ]
        for key in expired:
            del self._locks[key]

    @contextmanager
    def lock(self, key: str):
        with self._guard:
            now = time.time()
            self._evict_unlocked(now)
            entry = self._locks.get(key)
            if entry is None:
                entry = _LockEntry(lock=threading.Lock(), last_used_at=now)
                self._locks[key] = entry
            entry.last_used_at = now
            lk = entry.lock
        lk.acquire()
        try:
            yield
        finally:
            with self._guard:
                ent = self._locks.get(key)
                if ent is not None:
                    ent.last_used_at = time.time()
            lk.release()


class ProcessedEventCache:
    """Sliding-window dedupe for (channel, event_id) pairs (Slack retries / MM duplicates)."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[tuple[str, str], float] = {}
        self._guard = threading.Lock()

    def is_duplicate_event(self, channel: str, event_ts: str) -> bool:
        key = (channel, event_ts)
        now = time.time()
        with self._guard:
            expired = [k for k, t in self._seen.items() if now - t > self._ttl_seconds]
            for k in expired:
                del self._seen[k]
            if key in self._seen:
                return True
            self._seen[key] = now
            return False
