"""Cursor thread conversation aggregate (one Slack/MM thread -> one Cursor agent context)."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ThreadConversation:
    """Maps a chat thread key to Cursor agent id and last assistant reply metadata."""

    thread_key: str
    agent_id: str | None
    last_message_id: str | None
    last_fingerprint: str | None

    @classmethod
    def empty(cls, thread_key: str) -> ThreadConversation:
        return cls(thread_key, None, None, None)

    def with_agent(self, agent_id: str) -> ThreadConversation:
        """Bind agent id; clears last reply metadata when the agent id changes."""
        if self.agent_id == agent_id:
            return self
        return replace(self, agent_id=agent_id, last_message_id=None, last_fingerprint=None)

    def with_last_reply(self, message_id: str, fingerprint: str) -> ThreadConversation:
        """Record last posted assistant message id and content fingerprint."""
        if self.agent_id is None:
            return self
        return replace(self, last_message_id=message_id, last_fingerprint=fingerprint)
