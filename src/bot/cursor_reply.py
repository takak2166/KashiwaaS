"""
Shared Cursor agent reply flow for chat bots (Slack, Mattermost).

Encapsulates ThreadStore mapping, duplicate assistant detection, and polling hooks.
Platform-specific I/O is injected via callbacks.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from redis.exceptions import RedisError
from valkey.exceptions import ValkeyError

from src.bot.kashiwaas_mention import is_duplicate_assistant_reply
from src.bot.thread_store import ThreadStore
from src.cursor.client import AgentStatus, CursorAPIError, CursorClient, CursorTimeoutError
from src.utils.logger import get_logger

logger = get_logger(__name__)


def fingerprint_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def thread_store_safe(fn: Callable[[], object], /, *, default: object | None = None) -> object:
    """Run a ThreadStore op; log and swallow Valkey/redis errors."""
    try:
        return fn()
    except (ValkeyError, RedisError) as e:
        logger.warning("ThreadStore operation failed (ignored): {}", e)
        return default


def run_cursor_reply(
    *,
    thread_store_key: str,
    question: str,
    thread_store: ThreadStore,
    cursor_client: CursorClient,
    on_poll: Callable[[float], None] | None,
    post_assistant_text: Callable[[str], None],
    post_plain: Callable[[str], None],
    react_add: Callable[[str], None],
    react_remove: Callable[[str], None],
) -> None:
    """
    Execute ask/followup, post the assistant reply, and manage reactions.

    Callers should add an initial \"processing\" reaction before invoking this.
    """
    try:
        agent_id = thread_store.get(thread_store_key)
        expected_previous_message_id = thread_store.get_last_message_id(thread_store_key)
        if agent_id:
            logger.info("Followup in thread {} -> agent {}", thread_store_key, agent_id)
            result = cursor_client.followup(
                agent_id,
                question,
                expected_previous_message_id=expected_previous_message_id,
                on_poll=on_poll,
            )
        else:
            logger.info("New question in thread {}: {}...", thread_store_key, question[:80])
            result = cursor_client.ask(
                question,
                expected_previous_message_id=expected_previous_message_id,
                on_poll=on_poll,
            )
            if result.status not in (AgentStatus.ERROR, AgentStatus.STOPPED):
                thread_store.set(thread_store_key, result.agent_id)

        if result.status in (AgentStatus.ERROR, AgentStatus.STOPPED):
            thread_store.remove(thread_store_key)
            react_remove("eyes")
            react_add("x")
            post_plain("Sorry, an error occurred while generating the response. Please try again later.")
            return

        latest_msg = cursor_client.get_latest_assistant_message_obj(result.messages)
        if not latest_msg:
            thread_store.remove(thread_store_key)
            react_remove("eyes")
            react_add("x")
            post_plain("Failed to retrieve a response. Please try again.")
            return

        last_sent_message_id = thread_store.get_last_message_id(thread_store_key)
        last_sent_fingerprint = thread_store.get_last_message_fingerprint(thread_store_key)
        current_fingerprint = fingerprint_text(latest_msg.text)

        def _dup() -> bool:
            return is_duplicate_assistant_reply(
                last_sent_message_id=last_sent_message_id,
                last_sent_fingerprint=last_sent_fingerprint,
                assistant_message_id=latest_msg.id,
                assistant_text_fingerprint=current_fingerprint,
            )

        if _dup():
            max_retries = cursor_client.conversation_retry_max_retries
            for attempt in range(max_retries):
                logger.info(
                    "Duplicate assistant message detected; retrying conversation fetch "
                    "(attempt={}/{}, thread={}, msg_id={})",
                    attempt + 1,
                    max_retries,
                    thread_store_key,
                    latest_msg.id,
                )
                refreshed = cursor_client.get_conversation_after_complete(
                    result.agent_id,
                    expected_previous_message_id=latest_msg.id,
                )
                latest = cursor_client.get_latest_assistant_message_obj(refreshed)
                if not latest:
                    break
                latest_msg = latest
                current_fingerprint = fingerprint_text(latest_msg.text)
                if not _dup():
                    break

            if _dup():
                react_remove("eyes")
                react_add("x")
                post_plain("The same response content keeps repeating. Please wait a moment and try again.")
                return

        logger.info("Sending assistant message: thread={}, msg_id={}", thread_store_key, latest_msg.id)
        thread_store.set_last_message_id(thread_store_key, latest_msg.id)
        thread_store.set_last_message_fingerprint(thread_store_key, current_fingerprint)

        post_assistant_text(latest_msg.text)

        react_remove("eyes")
        react_add("white_check_mark")

    except CursorTimeoutError:
        thread_store_safe(lambda: thread_store.remove(thread_store_key))
        react_remove("eyes")
        react_add("x")
        post_plain(
            "Response generation timed out (agent did not finish within the poll timeout). "
            "Please shorten your question, split the task, or ask an admin to raise CURSOR_POLL_TIMEOUT."
        )
    except CursorAPIError as e:
        logger.error("Cursor API error: {}", e)
        react_remove("eyes")
        react_add("x")
        if e.status_code in (401, 403):
            post_plain("There is an issue with Cursor API authentication settings. Please contact an administrator.")
        else:
            thread_store_safe(lambda: thread_store.remove(thread_store_key))
            post_plain("Sorry, failed to retrieve a response. Please try again later.")
    except Exception as e:
        logger.error("Unexpected error handling mention: {}", e)
        thread_store_safe(lambda: thread_store.remove(thread_store_key))
        react_remove("eyes")
        react_add("x")
        post_plain("An unexpected error occurred. Please try again later.")
