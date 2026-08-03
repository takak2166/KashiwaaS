"""
Shared Cursor agent reply flow for chat bots (Slack, Mattermost).

Encapsulates conversation persistence, duplicate assistant detection, and polling hooks.
Platform-specific I/O is injected via :class:`~src.bot.application.chat_adapter.ChatAdapter`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from redis.exceptions import RedisError
from valkey.exceptions import ValkeyError

from src.bot.application.chat_adapter import ChatAdapter
from src.bot.application.processing_state import ProcessingState
from src.bot.domain.repository import ThreadConversationRepository
from src.cursor.client import AgentStatus, CursorAPIError, CursorClient, CursorTimeoutError
from src.utils.logger import get_logger

logger = get_logger(__name__)


def fingerprint_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def clear_conversation(repo: ThreadConversationRepository, thread_key: str) -> bool:
    """Delete mapping; return False and log at error if Valkey/redis fails (do not swallow silently)."""
    try:
        repo.delete(thread_key)
        return True
    except (ValkeyError, RedisError) as e:
        logger.error("Failed to clear conversation mapping thread={}: {}", thread_key, e)
        return False


def _fail_after_clear(
    *,
    repo: ThreadConversationRepository,
    thread_key: str,
    adapter: ChatAdapter,
    user_message: str,
    clear: bool = True,
) -> None:
    cleared = True
    if clear:
        cleared = clear_conversation(repo, thread_key)
    adapter.react(ProcessingState.FAILED)
    if clear and not cleared:
        adapter.post_plain(
            f"{user_message} "
            "Conversation state could not be reset; please contact an administrator if replies look stuck."
        )
    else:
        adapter.post_plain(user_message)


def run_cursor_reply(
    *,
    thread_key: str,
    question: str,
    repo: ThreadConversationRepository,
    cursor: CursorClient,
    adapter: ChatAdapter,
    on_poll: Callable[[float], None] | None,
) -> None:
    """
    Execute ask/followup, post the assistant reply, and manage reactions.

    Callers should add an initial \"processing\" reaction before invoking this.
    """
    try:
        convo = repo.get(thread_key)
        agent_id = convo.agent_id
        expected_previous_message_id = convo.last_message_id
        if agent_id:
            logger.info("Followup in thread {} -> agent {}", thread_key, agent_id)
            result = cursor.followup(
                agent_id,
                question,
                expected_previous_message_id=expected_previous_message_id,
                on_poll=on_poll,
            )
        else:
            logger.info("New question in thread {}: {}...", thread_key, question[:80])
            result = cursor.ask(
                question,
                expected_previous_message_id=expected_previous_message_id,
                on_poll=on_poll,
            )

        if result.status in (AgentStatus.ERROR, AgentStatus.STOPPED):
            _fail_after_clear(
                repo=repo,
                thread_key=thread_key,
                adapter=adapter,
                user_message="Sorry, an error occurred while generating the response. Please try again later.",
            )
            return

        latest_msg = cursor.get_latest_assistant_message_obj(result.messages)
        if not latest_msg:
            _fail_after_clear(
                repo=repo,
                thread_key=thread_key,
                adapter=adapter,
                user_message="Failed to retrieve a response. Please try again.",
            )
            return

        current_fingerprint = fingerprint_text(latest_msg.text)

        def _dup() -> bool:
            return convo.is_duplicate(message_id=latest_msg.id, fingerprint=current_fingerprint)

        if _dup():
            max_retries = cursor.conversation_retry_max_retries
            for attempt in range(max_retries):
                logger.info(
                    "Duplicate assistant message detected; retrying conversation fetch "
                    "(attempt={}/{}, thread={}, msg_id={})",
                    attempt + 1,
                    max_retries,
                    thread_key,
                    latest_msg.id,
                )
                refreshed = cursor.get_conversation_after_complete(
                    result.agent_id,
                    expected_previous_message_id=latest_msg.id,
                )
                latest = cursor.get_latest_assistant_message_obj(refreshed)
                if not latest:
                    break
                latest_msg = latest
                current_fingerprint = fingerprint_text(latest_msg.text)
                if not _dup():
                    break

            if _dup():
                adapter.react(ProcessingState.FAILED)
                adapter.post_plain("The same response content keeps repeating. Please wait a moment and try again.")
                return

        logger.info("Sending assistant message: thread={}, msg_id={}", thread_key, latest_msg.id)
        convo = convo.with_agent(result.agent_id).with_last_reply(latest_msg.id, current_fingerprint)
        repo.save(convo)

        adapter.post_assistant(latest_msg.text)

        adapter.react(ProcessingState.SUCCESS)

    except CursorTimeoutError:
        _fail_after_clear(
            repo=repo,
            thread_key=thread_key,
            adapter=adapter,
            user_message=(
                "Response generation timed out (agent did not finish within the poll timeout). "
                "Please shorten your question, split the task, or ask an admin to raise CURSOR_POLL_TIMEOUT."
            ),
        )
    except CursorAPIError as e:
        logger.exception("Cursor API error")
        if e.status_code in (401, 403):
            _fail_after_clear(
                repo=repo,
                thread_key=thread_key,
                adapter=adapter,
                user_message=(
                    "There is an issue with Cursor API authentication settings. Please contact an administrator."
                ),
                clear=False,
            )
        else:
            _fail_after_clear(
                repo=repo,
                thread_key=thread_key,
                adapter=adapter,
                user_message="Sorry, failed to retrieve a response. Please try again later.",
            )
    except (ValkeyError, RedisError):
        # Persistence failure must not clear an existing healthy mapping (e.g. save after Cursor success).
        logger.exception("ThreadConversationRepository error thread={}", thread_key)
        adapter.react(ProcessingState.FAILED)
        adapter.post_plain("Temporary storage error. Please try again later.")
    except Exception:
        logger.exception("Unexpected error handling mention")
        _fail_after_clear(
            repo=repo,
            thread_key=thread_key,
            adapter=adapter,
            user_message="An unexpected error occurred. Please try again later.",
        )
