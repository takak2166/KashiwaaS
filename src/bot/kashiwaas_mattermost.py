"""
KashiwaaS Mattermost bot: WebSocket (PAT) + Cursor Cloud Agents API.
Run as ``python -m src.bot.kashiwaas_mattermost``. Operate one process per bot to avoid duplicate replies.
"""

from __future__ import annotations

from src.bot.adapters.mattermost.app import (
    POLL_PROGRESS_POST_INTERVAL_SECONDS,
    PROCESSED_EVENT_TTL_SECONDS,
    THREAD_LOCK_TTL_SECONDS,
    _mattermost_wss_ssl_context,
    _resolve_mattermost_bot_user_id,
    build_websocket_handler,
    create_mattermost_stack,
    handle_mattermost_mention,
    main,
)

__all__ = [
    "POLL_PROGRESS_POST_INTERVAL_SECONDS",
    "PROCESSED_EVENT_TTL_SECONDS",
    "THREAD_LOCK_TTL_SECONDS",
    "_mattermost_wss_ssl_context",
    "_resolve_mattermost_bot_user_id",
    "build_websocket_handler",
    "create_mattermost_stack",
    "handle_mattermost_mention",
    "main",
]


if __name__ == "__main__":
    main()
