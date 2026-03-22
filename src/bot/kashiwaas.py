"""
KashiwaaS Bot Module
Slack Socket Mode application that answers questions via Cursor Cloud Agents API.
"""

import hashlib
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.bot.alerter import init_alerter
from src.bot.kashiwaas_mention import (
    extract_question,
    is_duplicate_assistant_reply,
    slack_mention_event_from_dict,
)
from src.bot.thread_store import ThreadStore
from src.cursor.client import (
    AgentStatus,
    CursorAPIError,
    CursorClient,
    CursorTimeoutError,
)
from src.utils.config import AppConfig, ConfigError, apply_dotenv, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_extract_question = extract_question  # tests import from kashiwaas

SLACK_MESSAGE_MAX_LENGTH = 4000
# Block Kit markdown block: standard Markdown in `text` (Slack converts for display).
# https://docs.slack.dev/reference/block-kit/blocks/markdown-block/
SLACK_MARKDOWN_BLOCK_TEXT_MAX = 12000
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


def create_app(cfg: AppConfig) -> App:
    """Create and configure the Slack Bolt application from loaded config."""
    if not cfg.bot.bot_token:
        raise ConfigError("SLACK_BOT_TOKEN is required for the bot")
    if not cfg.cursor.api_key:
        raise ConfigError("CURSOR_API_KEY is required for the bot")

    app = App(token=cfg.bot.bot_token)

    cursor_client = CursorClient(
        api_key=cfg.cursor.api_key,
        source_repository=cfg.cursor.source_repository,
        source_ref=cfg.cursor.source_ref,
        poll_interval=cfg.cursor.poll_interval,
        poll_timeout=cfg.cursor.poll_timeout,
        model=cfg.cursor.model,
        conversation_retry_max_retries=cfg.cursor.conversation_retry_max_retries,
        conversation_retry_delay_seconds=cfg.cursor.conversation_retry_delay_seconds,
    )

    @app.event("app_mention")
    def handle_mention(ack, event, say, client):
        _handle_mention(ack, event, say, client, cursor_client)

    @app.event("message")
    def handle_message_events(body, logger):
        logger.info(body)

    return app


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
        if rest.startswith("\n"):
            rest = rest[1:]
        elif rest.startswith(" "):
            rest = rest[1:]
        text = rest

    return chunks


def _fallback_notification_text(text: str, max_len: int = SLACK_MESSAGE_MAX_LENGTH) -> str:
    """Plain `text` for chat.postMessage (notifications, search); keep under Slack limits."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _say_markdown_chunks(say, chunks: list[str], thread_ts: str) -> None:
    """Post assistant content using Block Kit `markdown` blocks (Slack renders GFM-style Markdown)."""
    for chunk in chunks:
        say(
            text=_fallback_notification_text(chunk),
            blocks=[{"type": "markdown", "text": chunk}],
            thread_ts=thread_ts,
        )


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
        expired = [k for k, t in _processed_events.items() if now - t > PROCESSED_EVENT_TTL_SECONDS]
        for k in expired:
            del _processed_events[k]
        if key in _processed_events:
            return True
        _processed_events[key] = now
        return False


def _handle_mention(ack, event, say, client, cursor_client: CursorClient):
    """Process an app_mention event."""
    ack()

    ev = slack_mention_event_from_dict(event)
    text = ev.raw_text
    channel = ev.channel
    event_ts = ev.event_ts
    thread_ts = ev.thread_ts

    if _is_duplicate_event(channel, event_ts):
        logger.info(f"Duplicate app_mention skipped: channel={channel}, ts={event_ts}")
        return

    logger.info(f"app_mention received: channel={channel}, ts={event_ts}, thread_ts={thread_ts}, text={text!r}")

    question = extract_question(text)
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
                    result = cursor_client.ask(question, expected_previous_message_id=expected_previous_message_id)
                    if result.status not in (AgentStatus.ERROR, AgentStatus.STOPPED):
                        thread_store.set(thread_ts, result.agent_id)

                if result.status in (AgentStatus.ERROR, AgentStatus.STOPPED):
                    thread_store.remove(thread_ts)
                    _remove_reaction(client, channel, event_ts, "eyes")
                    _add_reaction(client, channel, event_ts, "x")
                    say(
                        text="Sorry, an error occurred while generating the response. Please try again later.",
                        thread_ts=thread_ts,
                    )
                    return

                latest_msg = cursor_client.get_latest_assistant_message_obj(result.messages)
                if not latest_msg:
                    thread_store.remove(thread_ts)
                    _remove_reaction(client, channel, event_ts, "eyes")
                    _add_reaction(client, channel, event_ts, "x")
                    say(text="Failed to retrieve a response. Please try again.", thread_ts=thread_ts)
                    return

                last_sent_message_id = thread_store.get_last_message_id(thread_ts)
                last_sent_fingerprint = thread_store.get_last_message_fingerprint(thread_ts)
                current_fingerprint = _fingerprint_text(latest_msg.text)

                def _dup() -> bool:
                    return is_duplicate_assistant_reply(
                        last_sent_message_id=last_sent_message_id,
                        last_sent_fingerprint=last_sent_fingerprint,
                        assistant_message_id=latest_msg.id,
                        assistant_text_fingerprint=current_fingerprint,
                    )

                if _dup():
                    max_retries = cursor_client.conversation_retry_max_retries
                    delay_seconds = cursor_client.conversation_retry_delay_seconds
                    for attempt in range(max_retries):
                        logger.info(
                            "Duplicate assistant message detected; retrying conversation fetch "
                            + (
                                f"(attempt={attempt + 1}/{max_retries}, thread_ts={thread_ts}, "
                                f"event_ts={event_ts}, msg_id={latest_msg.id})"
                            )
                        )
                        if attempt > 0:
                            time.sleep(delay_seconds * (2 ** (attempt - 1)))
                        refreshed = cursor_client.get_conversation(result.agent_id)
                        latest = cursor_client.get_latest_assistant_message_obj(refreshed)
                        if not latest:
                            break
                        latest_msg = latest
                        current_fingerprint = _fingerprint_text(latest_msg.text)
                        if not _dup():
                            break

                    if _dup():
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
                thread_store.set_last_message_id(thread_ts, latest_msg.id)
                thread_store.set_last_message_fingerprint(thread_ts, current_fingerprint)

                chunks = _split_message(latest_msg.text, max_length=SLACK_MARKDOWN_BLOCK_TEXT_MAX)
                _say_markdown_chunks(say, chunks, thread_ts)

                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "white_check_mark")

            except CursorTimeoutError:
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
                    thread_store.remove(thread_ts)
                    say(
                        text="Sorry, failed to retrieve a response. Please try again later.",
                        thread_ts=thread_ts,
                    )
            except Exception as e:
                logger.error(f"Unexpected error handling mention: {e}")
                thread_store.remove(thread_ts)
                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "x")
                say(
                    text="An unexpected error occurred. Please try again later.",
                    thread_ts=thread_ts,
                )

    threading.Thread(target=_process, daemon=True).start()


def main() -> None:
    """Entry point for the kashiwaas bot."""
    apply_dotenv()
    cfg = load_config()
    init_alerter(cfg)

    if not cfg.bot.app_token:
        logger.error("SLACK_APP_TOKEN is required for the bot")
        sys.exit(1)

    try:
        app = create_app(cfg)
    except ConfigError as e:
        logger.error("%s", e)
        sys.exit(1)

    handler = SocketModeHandler(
        app=app,
        app_token=cfg.bot.app_token,
    )
    logger.info("KashiwaaS bot starting...")
    handler.start()


if __name__ == "__main__":
    main()
