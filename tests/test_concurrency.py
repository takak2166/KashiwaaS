"""Unit tests for ThreadLockRegistry / ProcessedEventCache (no module-level state)."""

from __future__ import annotations

import threading
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

    def test_held_lock_not_evicted_during_wait(self) -> None:
        """C3: entry with holders>0 must not be replaced while another thread waits."""
        reg = ThreadLockRegistry(ttl_seconds=0)
        entered = threading.Event()
        release = threading.Event()
        second_done = threading.Event()
        errors: list[BaseException] = []

        def holder() -> None:
            with reg.lock("same"):
                entered.set()
                release.wait(timeout=2.0)

        def waiter() -> None:
            try:
                entered.wait(timeout=2.0)
                time.sleep(0.02)
                with reg.lock("same"):
                    second_done.set()
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=waiter)
        t1.start()
        t2.start()
        assert entered.wait(timeout=2.0)
        with reg._guard:  # noqa: SLF001
            reg._evict_unlocked(time.time() + 10)  # noqa: SLF001
            assert "same" in reg._locks  # noqa: SLF001
            assert reg._locks["same"].holders >= 1  # noqa: SLF001
        release.set()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)
        assert not errors
        assert second_done.is_set()
