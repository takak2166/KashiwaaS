"""In-memory dedupe stores (M1); replace with shared backend in production if needed."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class DedupeStore:
    """Sliding-window dedupe: first sight returns False, duplicates return True."""

    ttl_seconds: int
    _seen: dict[str, float] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def _evict(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > self.ttl_seconds]
        for k in expired:
            del self._seen[k]

    def is_duplicate(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._evict(now)
            if key in self._seen:
                return True
            self._seen[key] = now
            return False

    def forget(self, key: str) -> None:
        with self._lock:
            self._seen.pop(key, None)
