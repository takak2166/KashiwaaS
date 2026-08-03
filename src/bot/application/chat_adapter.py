"""Platform-neutral chat surface port for posting replies and reactions."""

from __future__ import annotations

from typing import Protocol

from src.bot.application.processing_state import ProcessingState


class ChatAdapter(Protocol):
    def post_plain(self, text: str) -> None:
        """Post user-visible plain text (errors, hints)."""

    def post_assistant(self, text: str) -> None:
        """Post the assistant reply (may chunk / format for the platform)."""

    def react(self, state: ProcessingState) -> None:
        """Finalize processing reactions (typically remove \"eyes\", add success or failure emoji)."""
