"""
Reporter Module
Provides functionality for generating and posting reports to Slack
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.analysis.daily import get_daily_stats
from src.analysis.visualization import create_weekly_report_charts
from src.analysis.weekly import get_weekly_stats
from src.bot.alerter import AlertLevel, alert
from src.bot.formatter import (
    format_chart_title,
    format_daily_report,
    format_dashboard_title,
    format_weekly_report,
)
from src.kibana.capture import KibanaCapture
from src.slack.client import SlackClient
from src.utils.date_utils import get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def generate_daily_report(
    channel_id: Optional[str] = None, target_date: Optional[datetime] = None, dry_run: bool = False
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
        error_msg = f"Failed to get channel info: {e}"
        logger.error(error_msg)

        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Daily Report - Channel Info Error",
            details={"channel_id": client.channel_id, "error": str(e)},
        )
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
        error_msg = f"Failed to get daily stats: {e}"
        logger.error(error_msg)

        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Daily Report - Stats Error",
            details={"channel": channel_name, "date": target_date.strftime("%Y-%m-%d"), "error": str(e)},
        )
        return

    # Format report message
    message = format_daily_report(stats)

    # Display report
    logger.info(f"Daily Report:\n{message}")

    # Post to Slack if not dry run
    if not dry_run:
        try:
            # Post message
            post_result = client.post_message(message)
            logger.info("Posted daily report to Slack")
            logger.info(f"Post result: {post_result}")
        except Exception as e:
            error_msg = f"Failed to post daily report: {e}"
            logger.error(error_msg)

            # Send alert
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Daily Report - Posting Error",
                details={"channel": channel_name, "date": target_date.strftime("%Y-%m-%d"), "error": str(e)},
            )
    else:
        logger.info("Dry run - not posting to Slack")


def generate_weekly_report(
    channel_id: Optional[str] = None, end_date: Optional[datetime] = None, dry_run: bool = False
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
        error_msg = f"Failed to get channel info: {e}"
        logger.error(error_msg)

        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Weekly Report - Channel Info Error",
            details={"channel_id": client.channel_id, "error": str(e)},
        )
        return

    # Get weekly stats
    try:
        stats = get_weekly_stats(channel_name, end_date)
        logger.info(f"Got weekly stats: {stats['message_count']} messages, {stats['reaction_count']} reactions")
    except Exception as e:
        error_msg = f"Failed to get weekly stats: {e}"
        logger.error(error_msg)

        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Weekly Report - Stats Error",
            details={
                "channel": channel_name,
                "period": f"{stats.get('start_date', 'unknown')} to {stats.get('end_date', 'unknown')}",
                "error": str(e),
            },
        )
        return

    # Create output directory
    reports_dir = Path("reports") / channel_name
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Generate charts
    try:
        chart_paths = create_weekly_report_charts(stats, str(reports_dir))
        logger.info(f"Generated charts: {chart_paths}")
    except Exception as e:
        error_msg = f"Failed to generate charts: {e}"
        logger.error(error_msg)

        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.WARNING,  # WARNING because we can continue without charts
            title="Weekly Report - Chart Generation Error",
            details={
                "channel": channel_name,
                "period": f"{stats['start_date']} to {stats['end_date']}",
                "error": str(e),
            },
        )
        chart_paths = {}

    # Capture Kibana dashboard if available
    kibana_screenshot = None
    try:
        kibana_capture = KibanaCapture()

        # Define dashboard ID as a variable
        WEEKLY_DASHBOARD_ID = os.getenv("KIBANA_WEEKLY_DASHBOARD_ID", f"{channel_name}-weekly")

        # Capture dashboard
        dashboard_path = str(reports_dir / "kibana_weekly_dashboard.png")
        kibana_capture.capture_dashboard(WEEKLY_DASHBOARD_ID, dashboard_path, time_range="7d", wait_for_render=10)
        kibana_screenshot = dashboard_path
        logger.info(f"Captured Kibana dashboard to {kibana_screenshot}")
    except Exception as e:
        error_msg = f"Failed to capture Kibana dashboard: {e}"
        logger.error(error_msg)

        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.WARNING,  # WARNING because we can continue without Kibana screenshot
            title="Weekly Report - Kibana Capture Error",
            details={
                "channel": channel_name,
                "period": f"{stats['start_date']} to {stats['end_date']}",
                "dashboard_id": os.getenv("KIBANA_WEEKLY_DASHBOARD_ID", f"{channel_name}-weekly"),
                "error": str(e),
            },
        )

    # Format report message
    message = format_weekly_report(
        start_date=stats["start_date"],
        end_date=stats["end_date"],
        total_messages=stats["message_count"],
        total_reactions=stats["reaction_count"],
        top_users=stats["user_stats"],
        top_posts=stats["top_posts"],
    )

    # Display report
    logger.info(f"Weekly Report:\n{message}")

    # Post to Slack if not dry run
    if not dry_run:
        try:
            # Post message
            client.post_message(message)

            # Upload charts
            for chart_type, chart_path in chart_paths.items():
                if chart_path:
                    client.upload_file(
                        chart_path,
                        format_chart_title(chart_type, f"{stats['start_date']} to {stats['end_date']}", is_weekly=True),
                    )

            # Upload Kibana screenshot
            if kibana_screenshot:
                client.upload_file(
                    kibana_screenshot,
                    format_dashboard_title(f"{stats['start_date']} to {stats['end_date']}", is_weekly=True),
                )

            logger.info("Posted weekly report to Slack")
        except Exception as e:
            error_msg = f"Failed to post weekly report: {e}"
            logger.error(error_msg)

            # Send alert
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Weekly Report - Posting Error",
                details={
                    "channel": channel_name,
                    "period": f"{stats['start_date']} to {stats['end_date']}",
                    "error": str(e),
                },
            )
    else:
        logger.info("Dry run - not posting to Slack")
