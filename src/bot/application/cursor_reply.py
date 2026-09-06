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
from src.cursor.client import FAILURE_STATUSES, CursorAPIError, CursorClient, CursorTimeoutError, RunStatus
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
    op = "unknown"
    try:
        convo = repo.get(thread_key)
        agent_id = convo.agent_id
        expected_previous_run_id = convo.last_message_id
        if agent_id:
            op = "followup"
            logger.info("Followup in thread {} -> agent {}", thread_key, agent_id)
            result = cursor.followup(
                agent_id,
                question,
                expected_previous_run_id=expected_previous_run_id,
                on_poll=on_poll,
            )
        else:
            op = "ask"
            logger.info("New question in thread {} (len={})", thread_key, len(question))
            result = cursor.ask(
                question,
                expected_previous_run_id=expected_previous_run_id,
                on_poll=on_poll,
            )

        if result.status in FAILURE_STATUSES:
            logger.warning(
                "Cursor run ended with status={} op={} thread={} agent={} run={}",
                result.status,
                op,
                thread_key,
                result.agent_id,
                result.run_id,
            )
            _fail_after_clear(
                repo=repo,
                thread_key=thread_key,
                adapter=adapter,
                user_message="Sorry, an error occurred while generating the response. Please try again later.",
            )
            return

        if result.status != RunStatus.FINISHED or not result.result_text:
            logger.warning(
                "No assistant result in Cursor response op={} thread={} agent={} run={} status={}",
                op,
                thread_key,
                result.agent_id,
                result.run_id,
                result.status,
            )
            _fail_after_clear(
                repo=repo,
                thread_key=thread_key,
                adapter=adapter,
                user_message="Failed to retrieve a response. Please try again.",
            )
            return

        run_id = result.run_id
        reply_text = result.result_text
        current_fingerprint = fingerprint_text(reply_text)

        if convo.last_message_id is not None and convo.last_message_id == run_id:
            logger.warning(
                "Stale run id returned op={} thread={} agent={} run_id={}",
                op,
                thread_key,
                result.agent_id,
                run_id,
            )
            adapter.react(ProcessingState.FAILED)
            adapter.post_plain("Failed to retrieve a new response. Please try again.")
            return

        logger.info("Sending assistant message: thread={}, run_id={}", thread_key, run_id)
        convo = convo.with_agent(result.agent_id).with_last_reply(run_id, current_fingerprint)
        repo.save(convo)

        adapter.post_assistant(reply_text)

        adapter.react(ProcessingState.SUCCESS)

    except CursorTimeoutError:
        logger.warning("Cursor poll timeout op={} thread={}", op, thread_key)
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
        logger.exception(
            "Cursor API error op={} thread={} status={}",
            op,
            thread_key,
            e.status_code,
        )
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
