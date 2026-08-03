"""Persistence ports for bot domain."""

from __future__ import annotations

from typing import Protocol

from src.bot.domain.conversation import ThreadConversation


class ThreadConversationRepository(Protocol):
    """Load and persist ``ThreadConversation`` for a chat thread key."""

    def get(self, thread_key: str) -> ThreadConversation:
        """Return persisted state or ``ThreadConversation.empty(thread_key)``."""

    def save(self, convo: ThreadConversation) -> None:
        """Upsert conversation state (including clearing optional hash fields)."""

    def delete(self, thread_key: str) -> None:
        """Remove mapping for ``thread_key`` if present."""
