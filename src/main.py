"""
Main Entry Point
This module serves as the entry point for the application.
"""
import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

from src.slack.client import SlackClient
from src.utils.config import config
from src.utils.date_utils import convert_from_timestamp, get_current_time
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
    fetch_all: bool = False
):
    """
    Fetch Slack messages for the specified period
    
    Args:
        days: Number of days to fetch
        channel_id: Channel ID to fetch from
        end_date: End date for fetching
        include_threads: Whether to include thread replies
        fetch_all: Whether to fetch all messages (ignores days and end_date)
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
        message_count = 0
        for message in client.get_messages(
            oldest=start_date,
            latest=end_date,
            include_threads=include_threads
        ):
            message_count += 1
            
            # TODO: Implement Elasticsearch storage
            # For now, just log the message information
            reactions_str = ", ".join([f"{r.name}({r.count})" for r in message.reactions])
            logger.debug(
                f"Message: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                f"by {message.username} ({message.user_id})\n"
                f"Text: {message.text}\n"
                f"Reactions: {reactions_str if message.reactions else 'None'}"
            )
            
            # Display progress every 100 messages
            if message_count % 100 == 0:
                logger.info(f"Processed {message_count} messages so far")
        
        logger.info(f"Completed. Total {message_count} messages processed")
        
    except Exception as e:
        logger.error(f"Error during message fetching: {e}")
        raise


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
            fetch_all=args.all
        )
    
    elif args.command == "report":
        # TODO: Implement report generation and posting
        logger.info(f"Report command not implemented yet. Type: {args.type}")
    
    else:
        logger.error("No command specified. Use --help for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()