"""Map Cursor replies and processing state to Slack channels / reactions."""

from __future__ import annotations

from typing import Any

from src.bot.application.processing_state import ProcessingState
from src.slack import markdown_blocks as _slack_md
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SlackChatAdapter:
    """Bolt ``say`` + ``client.reactions_*`` bound to one app_mention event."""

    def __init__(
        self,
        *,
        client: Any,
        channel: str,
        event_ts: str,
        say: Any,
        thread_ts: str,
    ):
        self._client = client
        self._channel = channel
        self._event_ts = event_ts
        self._say = say
        self._thread_ts = thread_ts

    def post_plain(self, text: str) -> None:
        self._say(text=text, thread_ts=self._thread_ts)

    def post_assistant(self, text: str) -> None:
        _slack_md.say_markdown_text(self._say, text, self._thread_ts)

    def react(self, state: ProcessingState) -> None:
        self._remove_reaction("eyes")
        emoji = "white_check_mark" if state == ProcessingState.SUCCESS else "x"
        self._add_reaction(emoji)

    def _add_reaction(self, name: str) -> None:
        try:
            self._client.reactions_add(channel=self._channel, timestamp=self._event_ts, name=name)
        except Exception as e:
            logger.error(
                "Failed to add reaction '{}' (channel={}, ts={}): {}",
                name,
                self._channel,
                self._event_ts,
                e,
            )

    def _remove_reaction(self, name: str) -> None:
        try:
            self._client.reactions_remove(channel=self._channel, timestamp=self._event_ts, name=name)
        except Exception as e:
            logger.warning("Failed to remove reaction '{}': {}", name, e)
