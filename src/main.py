"""
Main Entry Point
This module serves as the entry point for the application.
"""
import argparse
import sys
from datetime import datetime, timedelta
from typing import List, Optional

from src.es_client.client import ElasticsearchClient
from src.es_client.index import get_index_name
from src.slack.client import SlackClient
from src.slack.message import SlackMessage
from src.utils.config import config
from src.utils.date_utils import get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Slack Message Analysis System")
    
    # Set up subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch Slack messages and store in Elasticsearch")
    fetch_parser.add_argument(
        "--days", type=int, default=1, help="Number of days to fetch (default: 1)"
    )
    fetch_parser.add_argument(
        "--channel", type=str, help="Channel ID to fetch (default: value from environment variable)"
    )
    fetch_parser.add_argument(
        "--end-date", type=str, help="End date for fetching (YYYY-MM-DD format, default: today)"
    )
    fetch_parser.add_argument(
        "--no-threads", action="store_true", help="Do not fetch thread replies"
    )
    fetch_parser.add_argument(
        "--all", action="store_true", help="Fetch all messages (ignores --days and --end-date)"
    )
    fetch_parser.add_argument(
        "--no-store", action="store_true", help="Do not store messages in Elasticsearch"
    )
    fetch_parser.add_argument(
        "--batch-size", type=int, default=500, help="Batch size for Elasticsearch bulk indexing (default: 500)"
    )
    
    # report command
    report_parser = subparsers.add_parser("report", help="Generate and post report to Slack")
    report_parser.add_argument(
        "--type", type=str, choices=["daily", "weekly"], default="daily",
        help="Report type (daily or weekly, default: daily)"
    )
    report_parser.add_argument(
        "--date", type=str, help="Target date for report (YYYY-MM-DD format, default: yesterday)"
    )
    report_parser.add_argument(
        "--dry-run", action="store_true", help="Display report content without posting"
    )
    
    return parser.parse_args()


def fetch_messages(
    days: int = 1,
    channel_id: Optional[str] = None,
    end_date: Optional[datetime] = None,
    include_threads: bool = True,
    fetch_all: bool = False,
    store_messages: bool = True,
    batch_size: int = 500
):
    """
    Fetch Slack messages for the specified period and process them
    
    Args:
        days: Number of days to fetch
        channel_id: Channel ID to fetch from
        end_date: End date for fetching
        include_threads: Whether to include thread replies
        fetch_all: Whether to fetch all messages (ignores days and end_date)
        store_messages: Whether to store messages in Elasticsearch
        batch_size: Batch size for Elasticsearch bulk indexing
    """
    # Set end_date to current time if not specified
    if end_date is None:
        end_date = get_current_time()
    
    # Calculate start_date based on days or set to None for all messages
    start_date = None if fetch_all else end_date - timedelta(days=days)
    
    if fetch_all:
        logger.info(f"Fetching all messages from channel")
    else:
        logger.info(
            f"Fetching messages for {days} days "
            f"(from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"
        )
    
    # Initialize Slack client
    client = SlackClient(channel_id=channel_id)
    
    # Get channel information
    try:
        channel_info = client.get_channel_info()
        channel_name = channel_info.get("name", "unknown")
        logger.info(f"Target channel: {channel_name} ({client.channel_id})")
    except Exception as e:
        logger.error(f"Failed to get channel info: {e}")
        return
    
    # Fetch messages
    try:
        messages = list(_fetch_slack_messages(client, start_date, end_date, include_threads))
        logger.info(f"Fetched {len(messages)} messages from Slack")
        
        # Process messages
        if store_messages:
            process_messages(messages, channel_name, batch_size)
        else:
            # Just log the messages
            for message in messages:
                log_message(message)
            
        logger.info(f"Completed. Total {len(messages)} messages processed")
        
    except Exception as e:
        logger.error(f"Error during message fetching: {e}")
        raise


def _fetch_slack_messages(
    client: SlackClient,
    start_date: Optional[datetime],
    end_date: datetime,
    include_threads: bool
) -> List[SlackMessage]:
    """
    Fetch messages from Slack
    
    Args:
        client: SlackClient instance
        start_date: Start date for fetching
        end_date: End date for fetching
        include_threads: Whether to include thread replies
        
    Yields:
        SlackMessage: Fetched messages
    """
    message_count = 0
    
    for message in client.get_messages(
        oldest=start_date,
        latest=end_date,
        include_threads=include_threads
    ):
        message_count += 1
        
        # Display progress every 100 messages
        if message_count % 100 == 0:
            logger.info(f"Fetched {message_count} messages so far")
        
        yield message


def log_message(message: SlackMessage) -> None:
    """
    Log message information
    
    Args:
        message: SlackMessage to log
    """
    reactions_str = ", ".join([f"{r.name}({r.count})" for r in message.reactions])
    logger.debug(
        f"Message: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
        f"by {message.username} ({message.user_id})\n"
        f"Text: {message.text}\n"
        f"Reactions: {reactions_str if message.reactions else 'None'}"
    )


def process_messages(
    messages: List[SlackMessage],
    channel_name: str,
    batch_size: int = 500
) -> None:
    """
    Process messages and store them in Elasticsearch
    
    Args:
        messages: List of SlackMessage objects
        channel_name: Channel name
        batch_size: Batch size for Elasticsearch bulk indexing
    """
    # Initialize Elasticsearch client
    try:
        es_client = ElasticsearchClient()
        logger.info("Connected to Elasticsearch")
    except Exception as e:
        logger.error(f"Failed to connect to Elasticsearch: {e}")
        logger.warning("Messages will not be stored in Elasticsearch")
        return
    
    # Process messages in batches
    messages_buffer: List[SlackMessage] = []
    
    for message in messages:
        # Log message information
        log_message(message)
        
        # Add message to buffer
        messages_buffer.append(message)
        
        # Process batch if buffer is full
        if len(messages_buffer) >= batch_size:
            _store_messages_batch(es_client, channel_name, messages_buffer, batch_size)
            messages_buffer = []
    
    # Process remaining messages in buffer
    if messages_buffer:
        _store_messages_batch(es_client, channel_name, messages_buffer, batch_size)


def _store_messages_batch(
    es_client: ElasticsearchClient,
    channel_name: str,
    messages: List[SlackMessage],
    batch_size: int
) -> None:
    """
    Store a batch of messages in Elasticsearch
    
    Args:
        es_client: ElasticsearchClient instance
        channel_name: Channel name
        messages: List of messages to store
        batch_size: Batch size for logging
    """
    try:
        result = es_client.index_slack_messages(channel_name, messages, batch_size)
        logger.info(
            f"Indexed {result.get('success', 0)} messages in Elasticsearch, "
            f"{result.get('failed', 0)} failed"
        )
    except Exception as e:
        logger.error(f"Failed to store messages in Elasticsearch: {e}")


def main():
    """Main execution function"""
    # Check configuration
    if not config:
        logger.error("Configuration is not properly loaded. Please check your .env file.")
        sys.exit(1)
    
    # Parse command line arguments
    args = parse_args()
    
    if args.command == "fetch":
        # Parse end date
        end_date = None
        if args.end_date and not args.all:
            try:
                end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
                # Add timezone information
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                logger.error(f"Invalid date format: {args.end_date}. Use YYYY-MM-DD format.")
                sys.exit(1)
        
        # Execute message fetching
        fetch_messages(
            days=args.days,
            channel_id=args.channel,
            end_date=end_date,
            include_threads=not args.no_threads,
            fetch_all=args.all,
            store_messages=not args.no_store,
            batch_size=args.batch_size
        )
    
    elif args.command == "report":
        # TODO: Implement report generation and posting
        logger.info(f"Report command not implemented yet. Type: {args.type}")
    
    else:
        logger.error("No command specified. Use --help for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()