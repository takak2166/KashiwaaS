"""Slack Bolt app assembly and ``app_mention`` handling for KashiwaaS."""

from slack_bolt import App

from src.bot.adapters.slack.chat_adapter import SlackChatAdapter
from src.bot.adapters.slack.mention_parser import bot_mention_from_slack_event, extract_question
from src.bot.adapters.valkey.thread_conversation_repo import ValkeyThreadConversationRepository
from src.bot.application.concurrency import ProcessedEventCache, ThreadLockRegistry
from src.bot.application.cursor_reply import run_cursor_reply
from src.bot.application.mention_service import MentionHandlerService
from src.bot.domain.repository import ThreadConversationRepository
from src.bot.infra.cursor_client_factory import build_cursor_client
from src.cursor.client import CursorClient
from src.slack import markdown_blocks as _slack_md
from src.utils.config import AppConfig, ConfigError
from src.utils.logger import get_logger

logger = get_logger(__name__)

_extract_question = extract_question  # tests import from kashiwaas

# Re-export for tests (implementation lives in src.slack.markdown_blocks)
SLACK_MESSAGE_MAX_LENGTH = _slack_md.SLACK_MESSAGE_MAX_LENGTH
SLACK_MARKDOWN_BLOCK_TEXT_MAX = _slack_md.SLACK_MARKDOWN_BLOCK_TEXT_MAX
_split_message = _slack_md.split_slack_message_text
_fallback_notification_text = _slack_md.fallback_notification_text
_say_markdown_chunks = _slack_md.say_markdown_chunks

PROCESSED_EVENT_TTL_SECONDS = 300
POLL_PROGRESS_POST_INTERVAL_SECONDS = 300
THREAD_LOCK_TTL_SECONDS = 86400


def create_app(cfg: AppConfig) -> App:
    """Create and configure the Slack Bolt application from loaded config."""
    if not cfg.bot.bot_token:
        raise ConfigError("SLACK_BOT_TOKEN is required for the bot")
    if not cfg.cursor.api_key:
        raise ConfigError("CURSOR_API_KEY is required for the bot")

    app = App(token=cfg.bot.bot_token)

    cursor_client = build_cursor_client(cfg)
    conversation_repo: ThreadConversationRepository = ValkeyThreadConversationRepository(cfg.valkey)
    mention_service = MentionHandlerService(
        ProcessedEventCache(PROCESSED_EVENT_TTL_SECONDS),
        ThreadLockRegistry(THREAD_LOCK_TTL_SECONDS),
    )

    @app.event("app_mention")
    def handle_mention(ack, event, say, client):
        _handle_mention(
            ack,
            event,
            say,
            client,
            cursor_client,
            conversation_repo,
            mention_service=mention_service,
        )

    @app.event("message")
    def handle_message_events(body, logger):
        event = body.get("event") if isinstance(body, dict) else None
        etype = event.get("type") if isinstance(event, dict) else None
        logger.debug("slack message event type={}", etype)

    return app


def _add_reaction(client, channel: str, timestamp: str, name: str) -> None:
    try:
        client.reactions_add(channel=channel, timestamp=timestamp, name=name)
    except Exception as e:
        logger.error(f"Failed to add reaction '{name}' (channel={channel}, ts={timestamp}): {e}")


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


def _handle_mention(
    ack,
    event,
    say,
    client,
    cursor_client: CursorClient,
    conversation_repo: ThreadConversationRepository,
    *,
    mention_service: MentionHandlerService,
):
    """Process an app_mention event. ``ack()`` must run first (Bolt contract)."""
    ack()

    mention = bot_mention_from_slack_event(event)
    channel, event_ts = mention.event_key
    thread_ts = mention.thread_key

    logger.debug(
        f"app_mention received: channel={channel}, ts={event_ts}, thread_ts={thread_ts}, text_len={len(mention.raw_text)}"
    )

    def on_empty_question() -> None:
        say(
            text="Please enter a question. Example: `@kashiwaas How do I use Python async?`",
            thread_ts=thread_ts,
        )

    def on_start() -> None:
        _add_reaction(client, channel, event_ts, "eyes")

    def process() -> None:
        adapter = SlackChatAdapter(
            client=client,
            channel=channel,
            event_ts=event_ts,
            say=say,
            thread_ts=thread_ts,
        )
        run_cursor_reply(
            thread_key=thread_ts,
            question=mention.question,
            repo=conversation_repo,
            cursor=cursor_client,
            adapter=adapter,
            on_poll=_make_poll_progress_notifier(say, thread_ts),
        )

    mention_service.handle(
        mention,
        on_empty_question=on_empty_question,
        on_start=on_start,
        process=process,
    )
