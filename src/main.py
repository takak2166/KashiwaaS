"""
Main Entry Point
This module serves as the entry point for the application.
"""
import argparse
import sys
from datetime import datetime, timedelta
from typing import List, Optional

import os
from pathlib import Path

from src.analysis.daily import get_daily_stats
from src.analysis.visualization import create_daily_report_charts, create_weekly_report_charts
from src.es_client.client import ElasticsearchClient
from src.es_client.index import get_index_name
from src.kibana.capture import KibanaCapture
from src.kibana.dashboard import KibanaDashboard
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
        "--channel", type=str, help="Channel ID to report on (default: value from environment variable)"
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


def generate_daily_report(
    channel_id: Optional[str] = None,
    target_date: Optional[datetime] = None,
    dry_run: bool = False
) -> None:
    """
    Generate daily report
    
    Args:
        channel_id: Channel ID
        target_date: Target date (default: yesterday)
        dry_run: Whether to only display report without posting
    """
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
    
    # Set target_date to yesterday if not specified
    if target_date is None:
        current_time = get_current_time()
        target_date = current_time - timedelta(days=1)
    
    logger.info(f"Generating daily report for {target_date.strftime('%Y-%m-%d')}")
    
    # Get daily stats
    try:
        stats = get_daily_stats(channel_name, target_date)
        logger.info(f"Got daily stats: {stats['message_count']} messages, {stats['reaction_count']} reactions")
    except Exception as e:
        logger.error(f"Failed to get daily stats: {e}")
        return
    
    # Create output directory
    reports_dir = Path("reports") / channel_name
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate charts
    try:
        chart_paths = create_daily_report_charts(stats, str(reports_dir))
        logger.info(f"Generated charts: {chart_paths}")
    except Exception as e:
        logger.error(f"Failed to generate charts: {e}")
        chart_paths = {}
    
    # Capture Kibana dashboard if available
    kibana_screenshot = None
    try:
        kibana = KibanaDashboard()
        kibana_capture = KibanaCapture()
        
        # Capture dashboard
        dashboard_path = str(reports_dir / f"kibana_daily_{stats['date']}.png")
        kibana_capture.capture_dashboard(
            "slack-daily-dashboard",
            dashboard_path,
            time_range="1d",
            wait_for_render=10
        )
        kibana_screenshot = dashboard_path
        logger.info(f"Captured Kibana dashboard to {kibana_screenshot}")
    except Exception as e:
        logger.error(f"Failed to capture Kibana dashboard: {e}")
    
    # Format report message
    message = f"*Daily Report for {stats['date']}*\n\n"
    message += f"• Total Messages: *{stats['message_count']}*\n"
    message += f"• Total Reactions: *{stats['reaction_count']}*\n\n"
    
    if stats['user_stats']:
        message += "*Top Active Users:*\n"
        for user in stats['user_stats'][:5]:
            message += f"• {user['username']}: {user['message_count']} messages\n"
        message += "\n"
    
    if stats['top_reactions']:
        message += "*Top Reactions:*\n"
        for reaction in stats['top_reactions'][:5]:
            message += f"• :{reaction['name']}: - {reaction['count']} times\n"
        message += "\n"
    
    # Display report
    logger.info(f"Daily Report:\n{message}")
    
    # Post to Slack if not dry run
    if not dry_run:
        try:
            # Post message
            post_result = client.post_message(message)
            
            # Upload charts
            for chart_type, chart_path in chart_paths.items():
                if chart_path:
                    client.upload_file(
                        chart_path,
                        f"Daily {chart_type.capitalize()} Chart - {stats['date']}",
                        post_result.get("ts")
                    )
            
            # Upload Kibana screenshot
            if kibana_screenshot:
                client.upload_file(
                    kibana_screenshot,
                    f"Kibana Dashboard - {stats['date']}",
                    post_result.get("ts")
                )
            
            logger.info("Posted daily report to Slack")
        except Exception as e:
            logger.error(f"Failed to post daily report: {e}")
    else:
        logger.info("Dry run - not posting to Slack")


def generate_weekly_report(
    channel_id: Optional[str] = None,
    end_date: Optional[datetime] = None,
    dry_run: bool = False
) -> None:
    """
    Generate weekly report
    
    Args:
        channel_id: Channel ID
        end_date: End date (default: yesterday)
        dry_run: Whether to only display report without posting
    """
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
    
    # Set end_date to yesterday if not specified
    if end_date is None:
        current_time = get_current_time()
        end_date = current_time - timedelta(days=1)
    
    # Calculate start_date (7 days before end_date)
    start_date = end_date - timedelta(days=6)
    
    logger.info(f"Generating weekly report from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Get daily stats for each day in the week
    daily_stats = []
    current_date = start_date
    while current_date <= end_date:
        try:
            stats = get_daily_stats(channel_name, current_date)
            daily_stats.append(stats)
            logger.info(f"Got daily stats for {current_date.strftime('%Y-%m-%d')}: {stats['message_count']} messages")
        except Exception as e:
            logger.error(f"Failed to get daily stats for {current_date.strftime('%Y-%m-%d')}: {e}")
        
        current_date += timedelta(days=1)
    
    if not daily_stats:
        logger.error("No data available for the specified period")
        return
    
    # Create output directory
    reports_dir = Path("reports") / channel_name
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate charts
    try:
        chart_paths = create_weekly_report_charts(daily_stats, str(reports_dir))
        logger.info(f"Generated charts: {chart_paths}")
    except Exception as e:
        logger.error(f"Failed to generate charts: {e}")
        chart_paths = {}
    
    # Capture Kibana dashboard if available
    kibana_screenshot = None
    try:
        kibana = KibanaDashboard()
        kibana_capture = KibanaCapture()
        
        # Capture dashboard
        dashboard_path = str(reports_dir / f"kibana_weekly_{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}.png")
        kibana_capture.capture_dashboard(
            "5a5c8dc5-990d-4255-85d3-bae91a697a36",  # Kibana dashboard ID
            dashboard_path,
            time_range="7d",
            wait_for_render=10
        )
        kibana_screenshot = dashboard_path
        logger.info(f"Captured Kibana dashboard to {kibana_screenshot}")
    except Exception as e:
        logger.error(f"Failed to capture Kibana dashboard: {e}")
    
    # Calculate weekly totals
    total_messages = sum(stats['message_count'] for stats in daily_stats)
    total_reactions = sum(stats['reaction_count'] for stats in daily_stats)
    
    # Aggregate user stats
    user_stats = {}
    for stats in daily_stats:
        for user in stats['user_stats']:
            username = user['username']
            count = user['message_count']
            if username in user_stats:
                user_stats[username] += count
            else:
                user_stats[username] = count
    
    # Sort users by message count
    top_users = [
        {"username": username, "message_count": count}
        for username, count in sorted(user_stats.items(), key=lambda x: x[1], reverse=True)
    ][:10]  # Top 10
    
    # Format report message
    message = f"*Weekly Report ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})*\n\n"
    message += f"• Total Messages: *{total_messages}*\n"
    message += f"• Total Reactions: *{total_reactions}*\n"
    message += f"• Daily Average: *{total_messages / len(daily_stats):.1f}* messages\n\n"
    
    if top_users:
        message += "*Top Active Users:*\n"
        for user in top_users[:5]:
            message += f"• {user['username']}: {user['message_count']} messages\n"
        message += "\n"
    
    # Add daily breakdown
    message += "*Daily Breakdown:*\n"
    for stats in daily_stats:
        message += f"• {stats['date']}: {stats['message_count']} messages, {stats['reaction_count']} reactions\n"
    
    # Display report
    logger.info(f"Weekly Report:\n{message}")
    
    # Post to Slack if not dry run
    if not dry_run:
        try:
            # Post message
            post_result = client.post_message(message)
            
            # Upload charts
            for chart_type, chart_path in chart_paths.items():
                if chart_path:
                    client.upload_file(
                        chart_path,
                        f"Weekly {chart_type.capitalize()} Chart - {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                        post_result.get("ts")
                    )
            
            # Upload Kibana screenshot
            if kibana_screenshot:
                client.upload_file(
                    kibana_screenshot,
                    f"Kibana Dashboard - {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                    post_result.get("ts")
                )
            
            logger.info("Posted weekly report to Slack")
        except Exception as e:
            logger.error(f"Failed to post weekly report: {e}")
    else:
        logger.info("Dry run - not posting to Slack")


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
        # Parse date
        target_date = None
        if args.date:
            try:
                target_date = datetime.strptime(args.date, "%Y-%m-%d")
            except ValueError:
                logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD format.")
                sys.exit(1)
        
        # Generate report
        if args.type == "daily":
            generate_daily_report(
                channel_id=args.channel,
                target_date=target_date,
                dry_run=args.dry_run
            )
        elif args.type == "weekly":
            generate_weekly_report(
                channel_id=args.channel,
                end_date=target_date,
                dry_run=args.dry_run
            )
        else:
            logger.error(f"Unknown report type: {args.type}")
            sys.exit(1)
    
    else:
        logger.error("No command specified. Use --help for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()