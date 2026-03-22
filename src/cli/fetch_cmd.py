"""Fetch subcommand: Slack → optional Elasticsearch."""

import sys
from collections.abc import Iterator
from datetime import datetime
from typing import Optional

from src.bot.alerter import AlertLevel, alert
from src.cli.fetch_pipeline import build_dummy_slack_raw_messages, resolve_fetch_window
from src.es_client.client import ElasticsearchClient
from src.slack.client import SlackClient
from src.slack.message import SlackMessage
from src.utils.config import AppConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_fetch_command(args, cfg: AppConfig) -> None:
    """Wire argparse namespace to clients and ``fetch_messages``."""
    end_date = None
    if args.end_date and not args.all:
        try:
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            logger.error(f"Invalid date format: {args.end_date}. Use YYYY-MM-DD format.")
            sys.exit(1)

    slack_client: Optional[SlackClient] = None
    if not args.dummy:
        channel_id = args.channel or cfg.slack.channel_id
        slack_client = SlackClient(token=cfg.slack.api_token, channel_id=channel_id, dummy=False)

    es_client: Optional[ElasticsearchClient] = None
    if not args.no_store:
        try:
            es_client = ElasticsearchClient(cfg.elasticsearch)
            logger.info("Connected to Elasticsearch")
        except Exception as e:
            error_msg = f"Failed to connect to Elasticsearch: {e}"
            logger.error(error_msg)
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Elasticsearch Connection Error",
                details={
                    "host": cfg.elasticsearch.host,
                    "error": str(e),
                },
            )
            sys.exit(1)

    fetch_messages(
        slack_client,
        es_client,
        days=args.days,
        channel_id=args.channel,
        end_date=end_date,
        include_threads=not args.no_threads,
        fetch_all=args.all,
        store_messages=not args.no_store,
        batch_size=args.batch_size,
        use_dummy=args.dummy,
    )


def _iter_dummy_slack_messages() -> tuple[str, Iterator[SlackMessage]]:
    channel_name, dummy_messages = build_dummy_slack_raw_messages(10)

    def gen() -> Iterator[SlackMessage]:
        for msg in dummy_messages:
            yield SlackMessage.from_slack_data(channel_name, msg)

    return channel_name, gen()


def fetch_messages(
    slack_client: Optional[SlackClient],
    es_client: Optional[ElasticsearchClient],
    days: int = 1,
    channel_id: Optional[str] = None,
    end_date: Optional[datetime] = None,
    include_threads: bool = True,
    fetch_all: bool = False,
    store_messages: bool = True,
    batch_size: int = 500,
    use_dummy: bool = False,
) -> None:
    """Fetch Slack messages for the specified period and process them."""
    if end_date is None:
        end_date = datetime.now()

    start_date, end_date = resolve_fetch_window(end_date, days, fetch_all)

    if use_dummy:
        logger.info("Using mock Slack data for testing")
        channel_name, messages_iter = _iter_dummy_slack_messages()
    else:
        if slack_client is None:
            raise ValueError("slack_client is required when use_dummy is False")
        client = slack_client
        try:
            channel_info = client.get_channel_info()
            channel_name = channel_info.get("name", "unknown")
            logger.info(f"Target channel: {channel_name} ({client.channel_id})")
        except Exception as e:
            error_msg = f"Failed to get channel info: {e}"
            logger.error(error_msg)
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Channel Info Error",
                details={"channel_id": client.channel_id, "error": str(e)},
            )
            return

        try:
            messages_iter = _fetch_slack_messages(client, start_date, end_date, include_threads)
        except Exception as e:
            error_msg = f"Error during message fetching: {e}"
            logger.error(error_msg)
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Message Fetch Error",
                details={
                    "channel": channel_name,
                    "start_date": start_date.isoformat() if start_date else "None",
                    "end_date": end_date.isoformat() if end_date else "None",
                    "error": str(e),
                },
            )
            raise

    if store_messages:
        if es_client is None:
            raise ValueError("es_client is required when store_messages is True")
        total = process_messages(es_client, messages_iter, channel_name, batch_size)
        logger.info(f"Completed. Total {total} messages processed")
    else:
        total = 0
        for message in messages_iter:
            log_message(message)
            total += 1
        logger.info(f"Completed. Total {total} messages processed")


def _fetch_slack_messages(
    client: SlackClient, start_date: Optional[datetime], end_date: datetime, include_threads: bool
) -> Iterator[SlackMessage]:
    message_count = 0
    for message in client.get_messages(oldest=start_date, latest=end_date, include_threads=include_threads):
        message_count += 1
        if message_count % 100 == 0:
            logger.info(f"Fetched {message_count} messages so far")
        yield message


def log_message(message: SlackMessage) -> None:
    reactions_str = ", ".join([f"{r.name}({r.count})" for r in message.reactions])
    logger.debug(
        f"Message: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
        f"by {message.username} ({message.user_id})\n"
        f"Text: {message.text}\n"
        f"Reactions: {reactions_str if message.reactions else 'None'}"
    )


def process_messages(
    es_client: ElasticsearchClient,
    messages: Iterator[SlackMessage],
    channel_name: str,
    batch_size: int = 500,
) -> int:
    """Buffer messages from iterator and bulk-index in chunks. Returns total count."""
    logger.info("Using injected Elasticsearch client")
    messages_buffer: list[SlackMessage] = []
    total = 0
    for message in messages:
        log_message(message)
        messages_buffer.append(message)
        total += 1
        if len(messages_buffer) >= batch_size:
            _store_messages_batch(es_client, channel_name, messages_buffer, batch_size)
            messages_buffer = []
    if messages_buffer:
        _store_messages_batch(es_client, channel_name, messages_buffer, batch_size)
    return total


def _store_messages_batch(
    es_client: ElasticsearchClient, channel_name: str, messages: list[SlackMessage], batch_size: int
) -> None:
    try:
        result = es_client.index_slack_messages(channel_name, messages, batch_size)
        logger.info(
            f"Indexed {result.get('success', 0)} messages in Elasticsearch, " f"{result.get('failed', 0)} failed"
        )
        if result.get("failed", 0) > 0:
            alert(
                message=f"Failed to index {result.get('failed', 0)} messages in Elasticsearch",
                level=AlertLevel.WARNING,
                title="Indexing Partial Failure",
                details={
                    "channel": channel_name,
                    "success": result.get("success", 0),
                    "failed": result.get("failed", 0),
                    "batch_size": batch_size,
                },
            )
    except Exception as e:
        error_msg = f"Failed to store messages in Elasticsearch: {e}"
        logger.error(error_msg)
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Elasticsearch Indexing Error",
            details={"channel": channel_name, "message_count": len(messages), "error": str(e)},
        )
