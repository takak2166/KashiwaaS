"""Orchestration for mention dedupe + per-thread serialization."""

from __future__ import annotations

import threading
from collections.abc import Callable

from src.bot.application.concurrency import ProcessedEventCache, ThreadLockRegistry


class MentionHandlerService:
    """Coordinates Slack/MM mention handling: event dedupe and thread-scoped locks."""

    def __init__(
        self,
        processed_cache: ProcessedEventCache,
        thread_lock_registry: ThreadLockRegistry,
    ) -> None:
        self._processed_cache = processed_cache
        self._thread_lock_registry = thread_lock_registry

    def is_duplicate_event(self, channel_id: str, event_id: str) -> bool:
        return self._processed_cache.is_duplicate_event(channel_id, event_id)

    def run_locked_in_background(self, thread_key: str, fn: Callable[[], None]) -> None:
        def _wrapped() -> None:
            with self._thread_lock_registry.lock(thread_key):
                fn()

        threading.Thread(target=_wrapped, daemon=True).start()
