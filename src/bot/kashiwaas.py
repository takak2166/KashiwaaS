"""
KashiwaaS Bot Module
Slack Socket Mode application that answers questions via Cursor Cloud Agents API.
"""

import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.bot.thread_store import ThreadStore
from src.cursor.client import (
    AgentStatus,
    CursorAPIError,
    CursorClient,
    CursorTimeoutError,
)
from src.utils.logger import get_logger

dotenv_path = Path(".env")
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = get_logger(__name__)

SLACK_MESSAGE_MAX_LENGTH = 4000
MENTION_PATTERN = re.compile(r"<@[\w]+>")
# Deduplicate by (channel, event_ts): skip processing if we already handled this event (e.g. Slack retry).
PROCESSED_EVENT_TTL_SECONDS = 300  # 5 minutes
_processed_events: dict[tuple[str, str], float] = {}
_processed_events_lock = threading.Lock()

thread_store = ThreadStore()

THREAD_LOCK_TTL_SECONDS = 86400  # 24 hours


@dataclass
class _ThreadLockEntry:
    lock: threading.Lock
    last_used_at: float = field(default_factory=time.time)


_thread_locks: dict[str, _ThreadLockEntry] = {}
_thread_locks_lock = threading.Lock()


def _evict_thread_locks(now: float) -> None:
    # Must be called under _thread_locks_lock
    expired_keys = [
        thread_ts
        for thread_ts, entry in _thread_locks.items()
        if now - entry.last_used_at > THREAD_LOCK_TTL_SECONDS and not entry.lock.locked()
    ]
    for thread_ts in expired_keys:
        del _thread_locks[thread_ts]


def _get_thread_lock(thread_ts: str) -> threading.Lock:
    with _thread_locks_lock:
        now = time.time()
        _evict_thread_locks(now)
        entry = _thread_locks.get(thread_ts)
        if entry is None:
            entry = _ThreadLockEntry(lock=threading.Lock(), last_used_at=now)
            _thread_locks[thread_ts] = entry
        entry.last_used_at = now
        return entry.lock


@contextmanager
def _thread_ts_lock(thread_ts: str):
    lock = _get_thread_lock(thread_ts)
    lock.acquire()
    try:
        yield
    finally:
        with _thread_locks_lock:
            entry = _thread_locks.get(thread_ts)
            if entry is not None:
                entry.last_used_at = time.time()
        lock.release()


def create_app() -> App:
    """Create and configure the Slack Bolt application."""
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    cursor_client = CursorClient(
        api_key=os.environ["CURSOR_API_KEY"],
        source_repository=os.environ.get(
            "CURSOR_SOURCE_REPOSITORY",
            "https://github.com/takak2166/KashiwaaS",
        ),
        source_ref=os.environ.get("CURSOR_SOURCE_REF", "main"),
        poll_interval=int(os.environ.get("CURSOR_POLL_INTERVAL", "5")),
        poll_timeout=int(os.environ.get("CURSOR_POLL_TIMEOUT", "300")),
        model=os.environ.get("CURSOR_MODEL", "composer-1.5"),
        conversation_retry_max_retries=int(
            os.environ.get("CURSOR_CONVERSATION_RETRY_MAX_RETRIES", "4")
        ),
        conversation_retry_delay_seconds=float(
            os.environ.get("CURSOR_CONVERSATION_RETRY_DELAY_SECONDS", "1.5")
        ),
    )

    @app.event("app_mention")
    def handle_mention(ack, event, say, client):
        _handle_mention(ack, event, say, client, cursor_client)

    @app.event("message")
    def handle_message_events(body, logger):
        logger.info(body)

    return app


def _extract_question(text: str) -> str:
    """Remove mention tags and extract the actual question text."""
    question = MENTION_PATTERN.sub("", text).strip()
    return question


def _fingerprint_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _split_message(text: str, max_length: int = SLACK_MESSAGE_MAX_LENGTH) -> list[str]:
    """Split a long message into chunks respecting Slack's character limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind(" ", 0, max_length)
        if split_pos <= 0:
            split_pos = max_length

        chunks.append(text[:split_pos])
        rest = text[split_pos:]
        # Strip the single delimiter at the split (newline or space) for consistent chunk boundaries
        if rest.startswith("\n"):
            rest = rest[1:]
        elif rest.startswith(" "):
            rest = rest[1:]
        text = rest

    return chunks


def _add_reaction(client, channel: str, timestamp: str, name: str) -> None:
    try:
        client.reactions_add(channel=channel, timestamp=timestamp, name=name)
    except Exception as e:
        logger.error(f"Failed to add reaction '{name}' (channel={channel}, ts={timestamp}): {e}")


def _remove_reaction(client, channel: str, timestamp: str, name: str) -> None:
    try:
        client.reactions_remove(channel=channel, timestamp=timestamp, name=name)
    except Exception as e:
        logger.warning(f"Failed to remove reaction '{name}': {e}")


def _is_duplicate_event(channel: str, event_ts: str) -> bool:
    """Return True if we already processed this event (idempotency)."""
    key = (channel, event_ts)
    now = time.time()
    with _processed_events_lock:
        # Evict old entries
        expired = [k for k, t in _processed_events.items() if now - t > PROCESSED_EVENT_TTL_SECONDS]
        for k in expired:
            del _processed_events[k]
        if key in _processed_events:
            return True
        _processed_events[key] = now
        return False


def _handle_mention(ack, event, say, client, cursor_client: CursorClient):
    """Process an app_mention event."""
    # Socket Mode requires ack within 3 seconds; ack first so Slack does not timeout.
    ack()

    text = event.get("text", "")
    channel = event.get("channel", "")
    event_ts = event.get("ts", "")
    thread_ts = event.get("thread_ts") or event_ts

    if _is_duplicate_event(channel, event_ts):
        logger.info(f"Duplicate app_mention skipped: channel={channel}, ts={event_ts}")
        return

    logger.info(f"app_mention received: channel={channel}, ts={event_ts}, thread_ts={thread_ts}, text={text!r}")

    question = _extract_question(text)
    if not question:
        say(text="Please enter a question. Example: `@kashiwaas How do I use Python async?`", thread_ts=thread_ts)
        return

    _add_reaction(client, channel, event_ts, "eyes")

    def _process():
        with _thread_ts_lock(thread_ts):
            try:
                agent_id = thread_store.get(thread_ts)

                expected_previous_message_id = thread_store.get_last_message_id(thread_ts)
                if agent_id:
                    logger.info(f"Followup in thread {thread_ts} -> agent {agent_id}")
                    result = cursor_client.followup(
                        agent_id, question, expected_previous_message_id=expected_previous_message_id
                    )
                else:
                    logger.info(f"New question in thread {thread_ts}: {question[:80]}...")
                    result = cursor_client.ask(
                        question, expected_previous_message_id=expected_previous_message_id
                    )
                    if result.status not in (AgentStatus.ERROR, AgentStatus.STOPPED):
                        thread_store.set(thread_ts, result.agent_id)

                if result.status in (AgentStatus.ERROR, AgentStatus.STOPPED):
                    # Clear mapping so the next mention creates a fresh agent.
                    thread_store.remove(thread_ts)
                    _remove_reaction(client, channel, event_ts, "eyes")
                    _add_reaction(client, channel, event_ts, "x")
                    say(
                        text="Sorry, an error occurred while generating the response. Please try again later.",
                        thread_ts=thread_ts,
                    )
                    return

                latest_msg = cursor_client.get_latest_assistant_message_message(result.messages)
                if not latest_msg:
                    thread_store.remove(thread_ts)
                    _remove_reaction(client, channel, event_ts, "eyes")
                    _add_reaction(client, channel, event_ts, "x")
                    say(text="Failed to retrieve a response. Please try again.", thread_ts=thread_ts)
                    return

                last_sent_message_id = thread_store.get_last_message_id(thread_ts)
                last_sent_fingerprint = thread_store.get_last_message_fingerprint(thread_ts)
                current_fingerprint = _fingerprint_text(latest_msg.text)

                def _is_duplicate() -> bool:
                    return (
                        (last_sent_message_id and latest_msg.id == last_sent_message_id)
                        or (last_sent_fingerprint and current_fingerprint == last_sent_fingerprint)
                    )

                if _is_duplicate():
                    max_retries = getattr(cursor_client, "conversation_retry_max_retries", 4)
                    delay_seconds = getattr(cursor_client, "conversation_retry_delay_seconds", 1.5)
                    for attempt in range(max_retries):
                        logger.info(
                            "Duplicate assistant message detected; retrying conversation fetch "
                            + (
                                f"(attempt={attempt + 1}/{max_retries}, thread_ts={thread_ts}, "
                                f"event_ts={event_ts}, msg_id={latest_msg.id})"
                            )
                        )
                        if attempt > 0:
                            time.sleep(delay_seconds * (2**(attempt - 1)))
                        refreshed = cursor_client.get_conversation(result.agent_id)
                        latest = cursor_client.get_latest_assistant_message_message(refreshed)
                        if not latest:
                            break
                        latest_msg = latest
                        current_fingerprint = _fingerprint_text(latest_msg.text)
                        if not _is_duplicate():
                            break

                    if _is_duplicate():
                        _remove_reaction(client, channel, event_ts, "eyes")
                        _add_reaction(client, channel, event_ts, "x")
                        say(
                            text="The same response content keeps repeating. Please wait a moment and try again.",
                            thread_ts=thread_ts,
                        )
                        return

                logger.info(
                    f"Sending assistant message: thread_ts={thread_ts}, event_ts={event_ts}, msg_id={latest_msg.id}"
                )
                # Set before sending to avoid re-sending the same message on retries/errors.
                thread_store.set_last_message_id(thread_ts, latest_msg.id)
                thread_store.set_last_message_fingerprint(thread_ts, current_fingerprint)

                chunks = _split_message(latest_msg.text)
                for chunk in chunks:
                    say(text=chunk, thread_ts=thread_ts)

                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "white_check_mark")

            except CursorTimeoutError:
                # Treat timeouts as a terminal failure for this agent; allow a fresh agent on retry.
                thread_store.remove(thread_ts)
                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "x")
                say(
                    text="Response generation timed out. Please shorten your question or try again.",
                    thread_ts=thread_ts,
                )
            except CursorAPIError as e:
                logger.error(f"Cursor API error: {e}")
                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "x")
                if e.status_code in (401, 403):
                    say(
                        text=(
                            "There is an issue with Cursor API authentication settings. "
                            "Please contact an administrator."
                        ),
                        thread_ts=thread_ts,
                    )
                else:
                    # For non-auth API errors, assume the agent is broken and clear the mapping.
                    thread_store.remove(thread_ts)
                    say(
                        text="Sorry, failed to retrieve a response. Please try again later.",
                        thread_ts=thread_ts,
                    )
            except Exception as e:
                logger.error(f"Unexpected error handling mention: {e}")
                # On unexpected errors, clear the mapping to avoid trapping the thread with a bad agent.
                thread_store.remove(thread_ts)
                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "x")
                say(
                    text="An unexpected error occurred. Please try again later.",
                    thread_ts=thread_ts,
                )

    threading.Thread(target=_process, daemon=True).start()


def main():
    """Entry point for the kashiwaas bot."""
    app = create_app()
    handler = SocketModeHandler(
        app=app,
        app_token=os.environ["SLACK_APP_TOKEN"],
    )
    logger.info("KashiwaaS bot starting...")
    handler.start()


if __name__ == "__main__":
    main()
