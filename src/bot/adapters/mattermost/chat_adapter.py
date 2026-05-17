"""Map Cursor replies and processing state to Mattermost posts / reactions."""

from __future__ import annotations

from src.bot.application.processing_state import ProcessingState
from src.mattermost.client import MattermostBotClient
from src.slack import markdown_blocks as _slack_md
from src.utils.logger import get_logger

logger = get_logger(__name__)

MM_MESSAGE_MAX_LEN = 16000


class MattermostChatAdapter:
    """REST posts + reactions bound to one ``posted`` mention event."""

    def __init__(
        self,
        *,
        mm: MattermostBotClient,
        bot_user_id: str,
        event_post_id: str,
        channel_id: str,
        root_post_id: str,
    ):
        self._mm = mm
        self._bot_user_id = bot_user_id
        self._event_post_id = event_post_id
        self._channel_id = channel_id
        self._root_post_id = root_post_id

    def post_plain(self, text: str) -> None:
        body = text.replace("\x00", "")
        self._mm.create_post(self._channel_id, body, root_id=self._root_post_id)

    def post_assistant(self, text: str) -> None:
        body = text.replace("\x00", "")
        chunks = _slack_md.split_slack_message_text(body, MM_MESSAGE_MAX_LEN)
        for chunk in chunks:
            self._mm.create_post(self._channel_id, chunk, root_id=self._root_post_id)

    def react(self, state: ProcessingState) -> None:
        try:
            self._mm.remove_reaction(self._bot_user_id, self._event_post_id, "eyes")
        except Exception as ex:
            logger.warning("Failed to remove reaction eyes: {}", ex)
        emoji = "white_check_mark" if state == ProcessingState.SUCCESS else "x"
        try:
            self._mm.add_reaction(self._bot_user_id, self._event_post_id, emoji)
        except Exception as ex:
            logger.error("Failed to add reaction {}: {}", emoji, ex)
