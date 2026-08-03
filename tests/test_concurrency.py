"""Unit tests for ThreadLockRegistry / ProcessedEventCache (no module-level state)."""

from __future__ import annotations

import time

from src.bot.application.concurrency import ProcessedEventCache, ThreadLockRegistry


class TestProcessedEventCache:
    def test_seen_marks_and_detects_duplicate(self) -> None:
        cache = ProcessedEventCache(ttl_seconds=300)
        key = ("C1", "1.0")
        assert cache.seen(key) is False
        assert cache.seen(key) is True

    def test_seen_expires(self) -> None:
        cache = ProcessedEventCache(ttl_seconds=0)
        key = ("C1", "1.0")
        assert cache.seen(key) is False
        time.sleep(0.02)
        assert cache.seen(key) is False


class TestThreadLockRegistry:
    def test_lock_serializes_and_evicts(self) -> None:
        reg = ThreadLockRegistry(ttl_seconds=0)
        with reg.lock("t1"):
            pass
        time.sleep(0.02)
        with reg.lock("t2"):
            assert "t1" not in reg._locks  # noqa: SLF001
