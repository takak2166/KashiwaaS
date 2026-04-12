"""
KashiwaaS Bot Module
Slack Socket Mode application that answers questions via Cursor Cloud Agents API.
"""

import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.bot.alerter import init_alerter
from src.bot.cursor_reply import run_cursor_reply
from src.bot.kashiwaas_mention import (
    extract_question,
    slack_mention_event_from_dict,
)
from src.bot.thread_store import ThreadStore
from src.cursor.client import CursorClient
from src.slack import markdown_blocks as _slack_md
from src.utils.config import AppConfig, ConfigError, apply_dotenv, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_extract_question = extract_question  # tests import from kashiwaas

# Re-export for tests (implementation lives in src.slack.markdown_blocks)
SLACK_MESSAGE_MAX_LENGTH = _slack_md.SLACK_MESSAGE_MAX_LENGTH
SLACK_MARKDOWN_BLOCK_TEXT_MAX = _slack_md.SLACK_MARKDOWN_BLOCK_TEXT_MAX
_split_message = _slack_md.split_slack_message_text
_fallback_notification_text = _slack_md.fallback_notification_text
_say_markdown_chunks = _slack_md.say_markdown_chunks

# Deduplicate by (channel, event_ts): skip processing if we already handled this event (e.g. Slack retry).
PROCESSED_EVENT_TTL_SECONDS = 300  # 5 minutes
_processed_events: dict[tuple[str, str], float] = {}
_processed_events_lock = threading.Lock()

# Post "still working" in the Slack thread while the Cursor agent runs.
POLL_PROGRESS_POST_INTERVAL_SECONDS = 300

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
        conversation_text_stabilize_interval_seconds=cfg.cursor.conversation_text_stabilize_interval_seconds,
        conversation_text_stabilize_required_matches=cfg.cursor.conversation_text_stabilize_required_matches,
        conversation_text_stabilize_max_rounds=cfg.cursor.conversation_text_stabilize_max_rounds,
    )
    thread_store = ThreadStore(cfg.valkey)

    @app.event("app_mention")
    def handle_mention(ack, event, say, client):
        _handle_mention(ack, event, say, client, cursor_client, thread_store)

    @app.event("message")
    def handle_message_events(body, logger):
        logger.info(body)

    return app


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


def _make_poll_progress_notifier(say, thread_ts: str):
    """Return on_poll(elapsed) that posts to the thread at fixed intervals."""
    next_at = float(POLL_PROGRESS_POST_INTERVAL_SECONDS)

    def _on_poll(elapsed: float) -> None:
        nonlocal next_at
        while elapsed >= next_at:
            try:
                say(
                    text=("Still generating a response... (This may take several minutes for complex tasks.)"),
                    thread_ts=thread_ts,
                )
            except Exception as e:
                logger.warning(f"Failed to post poll progress (thread_ts={thread_ts}): {e}")
            next_at += POLL_PROGRESS_POST_INTERVAL_SECONDS

    return _on_poll


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


def _handle_mention(ack, event, say, client, cursor_client: CursorClient, thread_store: ThreadStore):
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

            def post_plain(t: str) -> None:
                say(text=t, thread_ts=thread_ts)

            def post_assistant(t: str) -> None:
                _slack_md.say_markdown_text(say, t, thread_ts)

            def react_add(name: str) -> None:
                _add_reaction(client, channel, event_ts, name)

            def react_remove(name: str) -> None:
                _remove_reaction(client, channel, event_ts, name)

            run_cursor_reply(
                thread_store_key=thread_ts,
                question=question,
                thread_store=thread_store,
                cursor_client=cursor_client,
                on_poll=_make_poll_progress_notifier(say, thread_ts),
                post_assistant_text=post_assistant,
                post_plain=post_plain,
                react_add=react_add,
                react_remove=react_remove,
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
