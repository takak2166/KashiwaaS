"""
KashiwaaS Bot Module
Slack Socket Mode application that answers questions via Cursor Cloud Agents API.
"""

import sys

from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.bot.adapters.slack.app import (
    POLL_PROGRESS_POST_INTERVAL_SECONDS,
    PROCESSED_EVENT_TTL_SECONDS,
    SLACK_MARKDOWN_BLOCK_TEXT_MAX,
    SLACK_MESSAGE_MAX_LENGTH,
    THREAD_LOCK_TTL_SECONDS,
    _extract_question,
    _fallback_notification_text,
    _handle_mention,
    _make_poll_progress_notifier,
    _say_markdown_chunks,
    _split_message,
    create_app,
)
from src.bot.alerter import init_alerter
from src.utils.config import ConfigError, apply_dotenv, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
