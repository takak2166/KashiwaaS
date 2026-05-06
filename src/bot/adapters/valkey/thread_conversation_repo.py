"""
Valkey (Redis protocol) persistence for :class:`~src.bot.domain.conversation.ThreadConversation`.

Hash fields match the former ``ThreadStore`` layout for backward-compatible keys on disk.
"""

from __future__ import annotations

from typing import Any

from valkey import Valkey

from src.bot.domain.conversation import ThreadConversation
from src.utils.config import ValkeyConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

_F_AGENT_ID = "agent_id"
_F_LAST_MESSAGE_ID = "last_message_id"
_F_LAST_FINGERPRINT = "last_message_fingerprint"


class ValkeyThreadConversationRepository:
    """ThreadConversationRepository backed by Valkey hashes with sliding TTL."""

    KEY_PREFIX = "kashiwaas:thread:"

    def __init__(self, cfg: ValkeyConfig, *, client: Any | None = None, key_prefix: str = ""):
        self._ttl = cfg.thread_ttl_seconds
        self._client: Any = client if client is not None else Valkey.from_url(cfg.url, decode_responses=True)
        self._key_prefix_suffix = key_prefix

    def _key(self, thread_key: str) -> str:
        return f"{self.KEY_PREFIX}{self._key_prefix_suffix}{thread_key}"

    def _refresh_ttl(self, key: str) -> None:
        if self._ttl > 0:
            self._client.expire(key, self._ttl)

    def get(self, thread_key: str) -> ThreadConversation:
        key = self._key(thread_key)
        agent_id, last_mid, last_fp = self._client.hmget(key, [_F_AGENT_ID, _F_LAST_MESSAGE_ID, _F_LAST_FINGERPRINT])
        if not agent_id:
            return ThreadConversation.empty(thread_key)
        self._refresh_ttl(key)
        return ThreadConversation(thread_key, agent_id, last_mid, last_fp)

    def save(self, convo: ThreadConversation) -> None:
        key = self._key(convo.thread_key)
        pipe = self._client.pipeline()
        if convo.agent_id is None:
            pipe.delete(key)
            pipe.execute()
            logger.debug("Deleted conversation mapping: {}", convo.thread_key)
            return

        pipe.hset(key, mapping={_F_AGENT_ID: convo.agent_id})
        if convo.last_message_id is None:
            pipe.hdel(key, _F_LAST_MESSAGE_ID)
        else:
            pipe.hset(key, _F_LAST_MESSAGE_ID, convo.last_message_id)
        if convo.last_fingerprint is None:
            pipe.hdel(key, _F_LAST_FINGERPRINT)
        else:
            pipe.hset(key, _F_LAST_FINGERPRINT, convo.last_fingerprint)
        if self._ttl > 0:
            pipe.expire(key, self._ttl)
        pipe.execute()
        logger.debug("Stored conversation: {} -> agent {}", convo.thread_key, convo.agent_id)

    def delete(self, thread_key: str) -> None:
        self._client.delete(self._key(thread_key))
