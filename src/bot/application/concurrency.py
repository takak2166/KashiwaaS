"""Process-local concurrency helpers for chat bot handlers."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class _LockEntry:
    lock: threading.Lock
    last_used_at: float = field(default_factory=time.time)
    holders: int = 0


class ThreadLockRegistry:
    """Serialize work per logical thread key within one Python process."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._locks: dict[str, _LockEntry] = {}
        self._guard = threading.Lock()

    def _evict_unlocked(self, now: float) -> None:
        # Evict only entries with no holders (avoids TOCTOU with Lock.locked()).
        expired = [
            key
            for key, entry in self._locks.items()
            if now - entry.last_used_at > self._ttl_seconds and entry.holders == 0
        ]
        for key in expired:
            del self._locks[key]

    @contextmanager
    def lock(self, key: str) -> Iterator[None]:
        with self._guard:
            now = time.time()
            self._evict_unlocked(now)
            entry = self._locks.get(key)
            if entry is None:
                entry = _LockEntry(lock=threading.Lock(), last_used_at=now)
                self._locks[key] = entry
            entry.holders += 1
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
                    ent.holders = max(0, ent.holders - 1)
            lk.release()


class ProcessedEventCache:
    """Sliding-window dedupe for (channel, event_id) pairs (Slack retries / MM duplicates)."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[tuple[str, str], float] = {}
        self._guard = threading.Lock()

    def seen(self, key: tuple[str, str]) -> bool:
        """Return True if ``key`` was already seen (and mark it on first sight)."""
        now = time.time()
        with self._guard:
            expired = [k for k, t in self._seen.items() if now - t > self._ttl_seconds]
            for k in expired:
                del self._seen[k]
            if key in self._seen:
                return True
            self._seen[key] = now
            return False
