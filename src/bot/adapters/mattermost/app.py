"""Mattermost WebSocket bot stack for KashiwaaS."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import sys
from dataclasses import replace
from typing import Any

import websockets
from mattermostdriver import Driver
from mattermostdriver.websocket import Websocket as MattermostDriverWebsocket
from websockets.asyncio.client import connect as ws_connect

from src.bot.adapters.mattermost.chat_adapter import MattermostChatAdapter
from src.bot.adapters.valkey.thread_conversation_repo import ValkeyThreadConversationRepository
from src.bot.alerter import init_alerter
from src.bot.application.concurrency import ProcessedEventCache, ThreadLockRegistry
from src.bot.application.mention_service import MentionHandlerService
from src.bot.cursor_reply import run_cursor_reply
from src.bot.domain.repository import ThreadConversationRepository
from src.bot.infra.cursor_client_factory import build_cursor_client
from src.bot.kashiwaas_mention import (
    MattermostPostedEvent,
    extract_question_mattermost,
    mattermost_posted_event_from_broadcast,
)
from src.cursor.client import CursorClient
from src.mattermost.client import MattermostBotClient
from src.utils.config import AppConfig, ConfigError, MattermostConfig, apply_dotenv, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

POLL_PROGRESS_POST_INTERVAL_SECONDS = 300
PROCESSED_EVENT_TTL_SECONDS = 300
THREAD_LOCK_TTL_SECONDS = 86400

_mm_driver_ws_log = logging.getLogger("mattermostdriver.websocket")


def _mattermost_wss_ssl_context(verify_tls: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    if not verify_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


class _MattermostWebsocketClientTls(MattermostDriverWebsocket):
    """Use a client TLS context for wss (upstream used ``Purpose.CLIENT_AUTH``).

    mattermostdriver 7.x ``websocket.py`` calls ``ssl.create_default_context`` with
    ``Purpose.CLIENT_AUTH``, which yields a server-role context; Python 3.14 then
    fails connecting with ``PROTOCOL_TLS_SERVER``. This class matches upstream
    ``connect`` except for the SSL purpose (and ``check_hostname`` when verify is off).
    """

    async def connect(self, event_handler: Any) -> None:
        scheme = "wss://"
        if self.options["scheme"] == "https":
            context: ssl.SSLContext | None = _mattermost_wss_ssl_context(self.options["verify"])
        else:
            scheme = "ws://"
            context = None

        url = "{scheme:s}{url:s}:{port:s}{basepath:s}/websocket".format(
            scheme=scheme,
            url=self.options["url"],
            port=str(self.options["port"]),
            basepath=self.options["basepath"],
        )

        self._alive = True

        while True:
            try:
                kw_args = {}
                if self.options["websocket_kw_args"] is not None:
                    kw_args = self.options["websocket_kw_args"]
                async with ws_connect(
                    url,
                    ssl=context,
                    **kw_args,
                ) as websocket:
                    await self._authenticate_websocket(websocket, event_handler)
                    while self._alive:
                        try:
                            await self._start_loop(websocket, event_handler)
                        except websockets.ConnectionClosed:
                            # Normal close (ConnectionClosedOK) and errors (ConnectionClosedError).
                            break
                if (not self.options["keepalive"]) or (not self._alive):
                    break
            except Exception as e:
                _mm_driver_ws_log.warning("Failed to establish websocket connection: %s", e)
                await asyncio.sleep(self.options["keepalive_delay"])


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


def _require_mattermost_bot_config(cfg: AppConfig) -> MattermostConfig:
    if cfg.mattermost is None:
        raise ConfigError(
            "Mattermost bot requires MATTERMOST_URL and MATTERMOST_PAT in the environment "
            "(optional MATTERMOST_BOT_USER_ID; resolved from PAT via users/me when unset)."
        )
    if not cfg.cursor.api_key:
        raise ConfigError("CURSOR_API_KEY is required for the Mattermost bot")
    return cfg.mattermost


def _resolve_mattermost_bot_user_id(mm_cfg: MattermostConfig, driver: Driver) -> MattermostConfig:
    """Fill ``bot_user_id`` from PAT login (``/api/v4/users/me``); optional env override must match."""
    api_id = str(getattr(getattr(driver, "client", None), "userid", None) or "").strip()
    if not api_id:
        raise ConfigError(
            "Mattermost PAT login did not return a user id; check MATTERMOST_URL, MATTERMOST_PAT, and TLS settings."
        )
    env_id = (mm_cfg.bot_user_id or "").strip()
    if env_id and env_id != api_id:
        raise ConfigError(
            f"MATTERMOST_BOT_USER_ID ({env_id!r}) does not match the PAT account id ({api_id!r}). "
            "Unset MATTERMOST_BOT_USER_ID to use the token user, or set it to that id."
        )
    if not env_id:
        logger.info("Mattermost bot user id from PAT (users/me): {}", api_id)
    return replace(mm_cfg, bot_user_id=api_id)


def handle_mattermost_mention(
    *,
    ev: MattermostPostedEvent,
    mm: MattermostBotClient,
    cursor_client: CursorClient,
    conversation_repo: ThreadConversationRepository,
    mention_service: MentionHandlerService,
    bot_user_id: str,
    bot_username: str = "",
) -> None:
    """Process a normalized Mattermost mention (runs reply in a background thread)."""
    thread_key = f"{ev.channel_id}:{ev.root_post_id}"
    text = ev.raw_text
    question = extract_question_mattermost(text, bot_user_id, bot_username=bot_username)

    if mention_service.is_duplicate_event(ev.channel_id, ev.event_post_id):
        logger.info("Duplicate posted event skipped: channel={} post={}", ev.channel_id, ev.event_post_id)
        return

    # Debug / troubleshooting: full mention post text (may contain secrets or PII).
    logger.debug(
        "mattermost mention: channel={} root={} post={} text={!r}",
        ev.channel_id,
        ev.root_post_id,
        ev.event_post_id,
        text,
    )

    if not question:
        hint = f"@{bot_username}" if (bot_username or "").strip() else f"@{bot_user_id}"
        mm.create_post(
            ev.channel_id,
            f"Please enter a question. Example: `{hint} How do I use Python async?`",
            root_id=ev.root_post_id,
        )
        return

    try:
        mm.add_reaction(bot_user_id, ev.event_post_id, "eyes")
    except Exception as e:
        logger.error("Failed to add eyes reaction: {}", e)

    def _process() -> None:
        adapter = MattermostChatAdapter(
            mm=mm,
            bot_user_id=bot_user_id,
            event_post_id=ev.event_post_id,
            channel_id=ev.channel_id,
            root_post_id=ev.root_post_id,
        )
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
            thread_key=thread_key,
            question=question,
            repo=conversation_repo,
            cursor_client=cursor_client,
            adapter=adapter,
            on_poll=on_poll,
        )

    mention_service.run_locked_in_background(thread_key, _process)


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
    conversation_repo: ThreadConversationRepository,
    mention_service: MentionHandlerService,
    bot_username: str,
):
    """Return async handler for mattermostdriver websocket."""

    async def on_message(message: str) -> None:
        # Debug only: MATTERMOST_LOG_RAW_WEBSOCKET dumps WebSocket payloads (may include tokens or message bodies).
        if mm_cfg.log_raw_websocket:
            logger.debug("mattermost websocket raw: {}", message[:4000])
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        if payload.get("event") != "posted":
            return
        data = _decode_posted_data(payload.get("data"))
        if not data:
            return
        ev = mattermost_posted_event_from_broadcast(
            data,
            bot_user_id=mm_cfg.bot_user_id,
            bot_username=bot_username,
        )
        if ev is None:
            return
        handle_mattermost_mention(
            ev=ev,
            mm=mm_client,
            cursor_client=cursor_client,
            conversation_repo=conversation_repo,
            mention_service=mention_service,
            bot_user_id=mm_cfg.bot_user_id,
            bot_username=bot_username,
        )

    return on_message


def _mattermost_bot_username(driver: Driver) -> str:
    """Login username for ``@name`` in open-channel posts (from PAT / users/me)."""
    u = getattr(getattr(driver, "client", None), "username", None)
    return u.strip() if isinstance(u, str) else ""


def create_mattermost_stack(
    cfg: AppConfig,
) -> tuple[MattermostConfig, Driver, CursorClient, ValkeyThreadConversationRepository, MattermostBotClient, str]:
    mm_cfg = _require_mattermost_bot_config(cfg)
    driver = Driver(_mattermost_driver_options(mm_cfg))
    driver.login()
    mm_cfg = _resolve_mattermost_bot_user_id(mm_cfg, driver)
    bot_username = _mattermost_bot_username(driver)
    mm_client = MattermostBotClient(driver)
    cursor_client = build_cursor_client(cfg)
    conversation_repo = ValkeyThreadConversationRepository(cfg.valkey, key_prefix="mm:")
    return mm_cfg, driver, cursor_client, conversation_repo, mm_client, bot_username


def main() -> None:
    apply_dotenv()
    cfg = load_config()
    init_alerter(cfg)
    try:
        mm_cfg, driver, cursor_client, conversation_repo, mm_client, bot_username = create_mattermost_stack(cfg)
    except ConfigError as e:
        logger.error("{}", e)
        sys.exit(1)

    mention_service = MentionHandlerService(
        ProcessedEventCache(PROCESSED_EVENT_TTL_SECONDS),
        ThreadLockRegistry(THREAD_LOCK_TTL_SECONDS),
    )
    handler = build_websocket_handler(
        mm_cfg=mm_cfg,
        mm_client=mm_client,
        cursor_client=cursor_client,
        conversation_repo=conversation_repo,
        mention_service=mention_service,
        bot_username=bot_username,
    )
    logger.info("KashiwaaS Mattermost bot starting (WebSocket)...")
    # mattermostdriver calls asyncio.get_event_loop(); CPython 3.12+ does not create
    # a default loop on the main thread, so set one before init_websocket.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    driver.init_websocket(handler, websocket_cls=_MattermostWebsocketClientTls)
