#!/usr/bin/env python
"""
Backfill Slack Messages

This script fetches historical Slack messages and stores them in Elasticsearch.
It can be used to backfill data for a specific date range.
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.es_client.client import ElasticsearchClient
from src.main import fetch_messages
from src.utils.config import config
from src.utils.date_utils import get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_date(date_str: str) -> datetime:
    """
    Parse date string in YYYY-MM-DD format
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        datetime: Parsed datetime object
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logger.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD format.")
        sys.exit(1)


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Backfill Slack messages")
    parser.add_argument(
        "--start-date", type=str, required=True,
        help="Start date for backfill (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--end-date", type=str,
        help="End date for backfill (YYYY-MM-DD format, default: today)"
    )
    parser.add_argument(
        "--channel", type=str,
        help="Channel ID to fetch (default: value from environment variable)"
    )
    parser.add_argument(
        "--no-threads", action="store_true",
        help="Do not fetch thread replies"
    )
    parser.add_argument(
        "--batch-days", type=int, default=7,
        help="Number of days to fetch in each batch (default: 7)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=500,
        help="Batch size for Elasticsearch bulk indexing (default: 500)"
    )
    
    args = parser.parse_args()
    
    # Check configuration
    if not config:
        logger.error("Configuration is not properly loaded. Please check your .env file.")
        sys.exit(1)
    
    # Parse dates
    start_date = parse_date(args.start_date)
    
    if args.end_date:
        end_date = parse_date(args.end_date)
        # Set to end of day
        end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        end_date = get_current_time()
    
    # Validate date range
    if start_date > end_date:
        logger.error("Start date must be before end date")
        sys.exit(1)
    
    logger.info(f"Backfilling messages from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Process in batches
    current_start = start_date
    batch_num = 1
    
    while current_start < end_date:
        # Calculate batch end date
        batch_end = current_start + timedelta(days=args.batch_days)
        if batch_end > end_date:
            batch_end = end_date
        
        logger.info(f"Processing batch {batch_num}: {current_start.strftime('%Y-%m-%d')} to {batch_end.strftime('%Y-%m-%d')}")
        
        # Fetch messages for this batch
        try:
            fetch_messages(
                days=(batch_end - current_start).days + 1,  # +1 to include the end date
                channel_id=args.channel,
                end_date=batch_end,
                include_threads=not args.no_threads,
                fetch_all=False,
                store_messages=True,
                batch_size=args.batch_size
            )
            logger.info(f"Completed batch {batch_num}")
        except Exception as e:
            logger.error(f"Error processing batch {batch_num}: {e}")
            sys.exit(1)
        
        # Move to next batch
        current_start = batch_end + timedelta(seconds=1)  # Start from the next second
        batch_num += 1
    
    logger.info("Backfill completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())