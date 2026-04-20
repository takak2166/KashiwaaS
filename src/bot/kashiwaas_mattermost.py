"""
KashiwaaS Mattermost bot: WebSocket (PAT) + Cursor Cloud Agents API.
Run as ``python -m src.bot.kashiwaas_mattermost``. Operate one process per bot to avoid duplicate replies.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from mattermostdriver import Driver

from src.bot.alerter import init_alerter
from src.bot.cursor_reply import run_cursor_reply
from src.bot.kashiwaas_mention import (
    MattermostPostedEvent,
    extract_question_mattermost,
    mattermost_posted_event_from_broadcast,
)
from src.bot.thread_store import ThreadStore
from src.cursor.client import CursorClient
from src.mattermost.client import MattermostBotClient
from src.slack import markdown_blocks as _slack_md
from src.utils.config import AppConfig, ConfigError, MattermostConfig, apply_dotenv, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

POLL_PROGRESS_POST_INTERVAL_SECONDS = 300
PROCESSED_EVENT_TTL_SECONDS = 300
THREAD_LOCK_TTL_SECONDS = 86400
MM_MESSAGE_MAX_LEN = 16000

_processed_events: dict[tuple[str, str], float] = {}
_processed_events_lock = threading.Lock()


@dataclass
class _ThreadLockEntry:
    lock: threading.Lock
    last_used_at: float = field(default_factory=time.time)


_thread_locks: dict[str, _ThreadLockEntry] = {}
_thread_locks_lock = threading.Lock()


def _evict_thread_locks(now: float) -> None:
    expired_keys = [
        k
        for k, entry in _thread_locks.items()
        if now - entry.last_used_at > THREAD_LOCK_TTL_SECONDS and not entry.lock.locked()
    ]
    for k in expired_keys:
        del _thread_locks[k]


def _get_thread_lock(key: str) -> threading.Lock:
    with _thread_locks_lock:
        now = time.time()
        _evict_thread_locks(now)
        entry = _thread_locks.get(key)
        if entry is None:
            entry = _ThreadLockEntry(lock=threading.Lock(), last_used_at=now)
            _thread_locks[key] = entry
        entry.last_used_at = now
        return entry.lock


@contextmanager
def _thread_key_lock(thread_key: str):
    lock = _get_thread_lock(thread_key)
    lock.acquire()
    try:
        yield
    finally:
        with _thread_locks_lock:
            ent = _thread_locks.get(thread_key)
            if ent is not None:
                ent.last_used_at = time.time()
        lock.release()


def _is_duplicate_event(channel_id: str, post_id: str) -> bool:
    key = (channel_id, post_id)
    now = time.time()
    with _processed_events_lock:
        expired = [k for k, t in _processed_events.items() if now - t > PROCESSED_EVENT_TTL_SECONDS]
        for k in expired:
            del _processed_events[k]
        if key in _processed_events:
            return True
        _processed_events[key] = now
        return False


def _mattermost_driver_options(mm: MattermostConfig) -> dict[str, Any]:
    return {
        "scheme": mm.driver_scheme,
        "url": mm.driver_host,
        "port": mm.driver_port,
        "basepath": "/api/v4",
        "token": mm.pat,
        "verify": mm.verify_tls,
        "keepalive": True,
        "timeout": 60,
    }


def _mm_escape_message(text: str) -> str:
    """Strip NULs only. Do not rewrite ``|``; global escaping broke tables and non-table pipes."""
    return text.replace("\x00", "")


def _post_mm_chunks(mm: MattermostBotClient, channel_id: str, root_id: str, text: str) -> None:
    body = _mm_escape_message(text)
    chunks = _slack_md.split_slack_message_text(body, MM_MESSAGE_MAX_LEN)
    for chunk in chunks:
        mm.create_post(channel_id, chunk, root_id=root_id)


def _require_mattermost_bot_config(cfg: AppConfig) -> MattermostConfig:
    if cfg.mattermost is None:
        raise ConfigError(
            "Mattermost bot requires MATTERMOST_URL, MATTERMOST_PAT, and MATTERMOST_BOT_USER_ID in the environment."
        )
    if not cfg.cursor.api_key:
        raise ConfigError("CURSOR_API_KEY is required for the Mattermost bot")
    return cfg.mattermost


def handle_mattermost_mention(
    *,
    ev: MattermostPostedEvent,
    mm: MattermostBotClient,
    cursor_client: CursorClient,
    thread_store: ThreadStore,
    bot_user_id: str,
) -> None:
    """Process a normalized Mattermost mention (runs reply in a background thread)."""
    thread_key = f"{ev.channel_id}:{ev.root_post_id}"
    text = ev.raw_text
    question = extract_question_mattermost(text, bot_user_id)

    if _is_duplicate_event(ev.channel_id, ev.event_post_id):
        logger.info("Duplicate posted event skipped: channel={} post={}", ev.channel_id, ev.event_post_id)
        return

    # Intentional: log full mention post text at INFO for troubleshooting (may contain secrets/PII).
    logger.info(
        "mattermost mention: channel={} root={} post={} text={!r}",
        ev.channel_id,
        ev.root_post_id,
        ev.event_post_id,
        text,
    )

    if not question:
        mm.create_post(
            ev.channel_id,
            "Please enter a question. Example: `@botuserid How do I use Python async?`",
            root_id=ev.root_post_id,
        )
        return

    try:
        mm.add_reaction(bot_user_id, ev.event_post_id, "eyes")
    except Exception as e:
        logger.error("Failed to add eyes reaction: {}", e)

    def _process() -> None:
        with _thread_key_lock(thread_key):

            def post_plain(t: str) -> None:
                mm.create_post(ev.channel_id, t, root_id=ev.root_post_id)

            def post_assistant(t: str) -> None:
                _post_mm_chunks(mm, ev.channel_id, ev.root_post_id, t)

            def react_add(name: str) -> None:
                try:
                    mm.add_reaction(bot_user_id, ev.event_post_id, name)
                except Exception as ex:
                    logger.error("Failed to add reaction {}: {}", name, ex)

            def react_remove(name: str) -> None:
                try:
                    mm.remove_reaction(bot_user_id, ev.event_post_id, name)
                except Exception as ex:
                    logger.warning("Failed to remove reaction {}: {}", name, ex)

            next_at = float(POLL_PROGRESS_POST_INTERVAL_SECONDS)

            def on_poll(elapsed: float) -> None:
                nonlocal next_at
                while elapsed >= next_at:
                    try:
                        mm.create_post(
                            ev.channel_id,
                            "Still generating a response... (This may take several minutes for complex tasks.)",
                            root_id=ev.root_post_id,
                        )
                    except Exception as ex:
                        logger.warning("Failed to post poll progress (root={}): {}", ev.root_post_id, ex)
                    next_at += POLL_PROGRESS_POST_INTERVAL_SECONDS

            run_cursor_reply(
                thread_store_key=thread_key,
                question=question,
                thread_store=thread_store,
                cursor_client=cursor_client,
                on_poll=on_poll,
                post_assistant_text=post_assistant,
                post_plain=post_plain,
                react_add=react_add,
                react_remove=react_remove,
            )

    threading.Thread(target=_process, daemon=True).start()


def _decode_posted_data(raw: Any) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("mattermost posted: invalid JSON in data: {!r}", raw[:500])
            return None
    return None


def build_websocket_handler(
    *,
    mm_cfg: MattermostConfig,
    mm_client: MattermostBotClient,
    cursor_client: CursorClient,
    thread_store: ThreadStore,
):
    """Return async handler for mattermostdriver websocket."""

    async def on_message(message: str) -> None:
        if mm_cfg.log_raw_websocket:
            logger.info("mattermost websocket raw: {}", message[:4000])
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        if payload.get("event") != "posted":
            return
        data = _decode_posted_data(payload.get("data"))
        if not data:
            return
        ev = mattermost_posted_event_from_broadcast(data, bot_user_id=mm_cfg.bot_user_id)
        if ev is None:
            return
        handle_mattermost_mention(
            ev=ev,
            mm=mm_client,
            cursor_client=cursor_client,
            thread_store=thread_store,
            bot_user_id=mm_cfg.bot_user_id,
        )

    return on_message


def create_mattermost_stack(
    cfg: AppConfig,
) -> tuple[MattermostConfig, Driver, CursorClient, ThreadStore, MattermostBotClient]:
    mm_cfg = _require_mattermost_bot_config(cfg)
    driver = Driver(_mattermost_driver_options(mm_cfg))
    driver.login()
    mm_client = MattermostBotClient(driver)
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
    thread_store = ThreadStore(cfg.valkey, key_prefix="mm:")
    return mm_cfg, driver, cursor_client, thread_store, mm_client


def main() -> None:
    apply_dotenv()
    cfg = load_config()
    init_alerter(cfg)
    try:
        mm_cfg, driver, cursor_client, thread_store, mm_client = create_mattermost_stack(cfg)
    except ConfigError as e:
        logger.error("{}", e)
        sys.exit(1)

    handler = build_websocket_handler(
        mm_cfg=mm_cfg,
        mm_client=mm_client,
        cursor_client=cursor_client,
        thread_store=thread_store,
    )
    logger.info("KashiwaaS Mattermost bot starting (WebSocket)...")
    driver.init_websocket(handler)


if __name__ == "__main__":
    main()
