"""Orchestration for mention dedupe + per-thread serialization."""

from __future__ import annotations

import threading
from collections.abc import Callable

from src.bot.application.concurrency import ProcessedEventCache, ThreadLockRegistry
from src.bot.domain.mention import BotMention
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MentionHandlerService:
    """Coordinates Slack/MM mention handling: event dedupe, eyes, and thread-scoped locks."""

    def __init__(
        self,
        processed_cache: ProcessedEventCache,
        thread_lock_registry: ThreadLockRegistry,
    ) -> None:
        self._processed_cache = processed_cache
        self._thread_lock_registry = thread_lock_registry

    def handle(
        self,
        mention: BotMention,
        *,
        on_empty_question: Callable[[], None],
        on_start: Callable[[], None],
        process: Callable[[], None],
    ) -> None:
        """
        Dedupe → empty-question hint → initial reaction → background locked process.

        Callers (adapters) must ``ack()`` before invoking this when the platform requires it.
        """
        if self._processed_cache.seen(mention.event_key):
            logger.info(
                "Duplicate mention skipped: event_key={} thread={}",
                mention.event_key,
                mention.thread_key,
            )
            return
        if not mention.question:
            on_empty_question()
            return
        on_start()
        self.run_locked_in_background(mention.thread_key, process)

    def run_locked_in_background(self, thread_key: str, fn: Callable[[], None]) -> None:
        def _wrapped() -> None:
            with self._thread_lock_registry.lock(thread_key):
                fn()

        threading.Thread(target=_wrapped, daemon=True).start()
