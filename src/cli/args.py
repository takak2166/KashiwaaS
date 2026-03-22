"""argparse definitions for ``python -m src.cli``."""

import argparse


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Slack Message Analysis System")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch Slack messages and store in Elasticsearch")
    fetch_parser.add_argument("--days", type=int, default=1, help="Number of days to fetch (default: 1)")
    fetch_parser.add_argument(
        "--channel", type=str, help="Channel ID to fetch (default: value from environment variable)"
    )
    fetch_parser.add_argument("--end-date", type=str, help="End date for fetching (YYYY-MM-DD format, default: today)")
    fetch_parser.add_argument("--no-threads", action="store_true", help="Do not fetch thread replies")
    fetch_parser.add_argument("--all", action="store_true", help="Fetch all messages (ignores --days and --end-date)")
    fetch_parser.add_argument("--no-store", action="store_true", help="Do not store messages in Elasticsearch")
    fetch_parser.add_argument(
        "--batch-size", type=int, default=500, help="Batch size for Elasticsearch bulk indexing (default: 500)"
    )
    fetch_parser.add_argument("--dummy", action="store_true", help="Use dummy data instead of fetching from Slack")

    report_parser = subparsers.add_parser("report", help="Generate and post report to Slack")
    report_parser.add_argument(
        "--type",
        type=str,
        choices=["daily", "weekly"],
        default="daily",
        help="Report type (daily or weekly, default: daily)",
    )
    report_parser.add_argument(
        "--channel", type=str, help="Channel ID to report on (default: value from environment variable)"
    )
    report_parser.add_argument(
        "--date", type=str, help="Target date for report (YYYY-MM-DD format, default: yesterday)"
    )
    report_parser.add_argument("--dry-run", action="store_true", help="Display report content without posting")

    return parser.parse_args()
