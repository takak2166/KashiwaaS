"""
Reporter Module
Provides functionality for generating and posting reports to Slack
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.analysis.daily import get_daily_stats
from src.analysis.visualization import create_weekly_report_charts
from src.analysis.weekly import get_weekly_stats
from src.bot.alerter import AlertLevel, alert
from src.bot.report_payloads import (
    build_daily_report_payload,
    build_weekly_report_payload,
)
from src.es_client.client import ElasticsearchClient
from src.kibana.capture import KibanaCapture
from src.slack.client import SlackClient
from src.utils.config import AppConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


def generate_daily_report(
    es_client: ElasticsearchClient,
    cfg: AppConfig,
    slack_client: Optional[SlackClient] = None,
    channel_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    target_date: Optional[datetime] = None,
    dry_run: bool = False,
) -> None:
    """
    Generate daily report

    Args:
        es_client: Elasticsearch client (caller constructs)
        slack_client: Slack client for channel info and posting (omit when dry_run)
        channel_id: Channel ID
        channel_name: Channel name (used when dry_run or after resolving from API)
        target_date: Target date (caller should supply; CLI uses ``src.cli`` default: yesterday)
        dry_run: Whether to only display report without posting
    """
    if not dry_run and slack_client is None:
        raise ValueError("slack_client is required when dry_run is False")

    client = slack_client
    if not dry_run:
        # Get channel information
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
                title="Daily Report - Channel Info Error",
                details={"channel_id": client.channel_id, "error": str(e)},
            )
            return

    if target_date is None:
        raise ValueError("target_date is required (set default in CLI / caller)")

    logger.info(f"Generating daily report for {target_date.strftime('%Y-%m-%d')}")

    # Get daily stats
    try:
        stats = get_daily_stats(
            channel_name or "",
            target_date,
            es_client,
            fallback_channel_name=cfg.slack.channel_name,
        )
        logger.info(f"Got daily stats: {stats.message_count} messages, {stats.reaction_count} reactions")
    except Exception as e:
        error_msg = f"Failed to get daily stats: {e}"
        logger.error(error_msg)

        if not dry_run:
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Daily Report - Stats Error",
                details={"channel": channel_name, "date": target_date.strftime("%Y-%m-%d"), "error": str(e)},
            )
        return

    payload = build_daily_report_payload(stats)

    # Display report
    logger.info(f"Daily Report:\n{payload.formatted_text}")

    # Post to Slack if not dry run
    if not dry_run and client is not None:
        try:
            post_result = client.post_message_markdown(payload.formatted_text)
            logger.info("Posted daily report to Slack")
            logger.info(f"Post result: {post_result}")
        except Exception as e:
            error_msg = f"Failed to post daily report: {e}"
            logger.error(error_msg)

            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Daily Report - Posting Error",
                details={"channel": channel_name, "date": target_date.strftime("%Y-%m-%d"), "error": str(e)},
            )
    else:
        logger.info("Dry run - not posting to Slack")


def generate_weekly_report(
    es_client: ElasticsearchClient,
    cfg: AppConfig,
    slack_client: Optional[SlackClient] = None,
    kibana_capture: Optional[KibanaCapture] = None,
    channel_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    end_date: Optional[datetime] = None,
    dry_run: bool = False,
) -> None:
    """
    Generate weekly report

    Args:
        es_client: Elasticsearch client (caller constructs)
        slack_client: Slack client for channel info and posting (omit when dry_run)
        kibana_capture: Kibana capture helper (optional; weekly dashboard screenshot)
        channel_id: Channel ID
        channel_name: Channel name
        end_date: End date (default: yesterday)
        dry_run: Whether to only display report without posting
    """
    if not dry_run and slack_client is None:
        raise ValueError("slack_client is required when dry_run is False")

    client = slack_client
    if not dry_run:
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
                title="Weekly Report - Channel Info Error",
                details={"channel_id": client.channel_id, "error": str(e)},
            )
            return

    weekly_dashboard_id = cfg.kibana.weekly_dashboard_id or f"{channel_name}-weekly"

    # Get weekly stats
    try:
        stats = get_weekly_stats(
            channel_name or "",
            es_client,
            end_date=end_date,
            fallback_channel_name=cfg.slack.channel_name,
        )
        logger.info(f"Got weekly stats: {stats.message_count} messages, {stats.reaction_count} reactions")
    except Exception as e:
        error_msg = f"Failed to get weekly stats: {e}"
        logger.error(error_msg)

        if not dry_run:
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Weekly Report - Stats Error",
                details={"channel": channel_name, "error": str(e)},
            )
        return

    if not stats.daily_stats:
        error_msg = "No data available for the specified period"
        logger.error(error_msg)
        if not dry_run:
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Weekly Report - No Data",
                details={"channel": channel_name},
            )
        return

    # Create output directory
    reports_dir = Path("reports") / (channel_name or "unknown")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Generate charts
    try:
        chart_paths = create_weekly_report_charts(stats, str(reports_dir))
        logger.info(f"Generated charts: {chart_paths}")
    except Exception as e:
        error_msg = f"Failed to generate charts: {e}"
        logger.error(error_msg)

        if not dry_run:
            alert(
                message=error_msg,
                level=AlertLevel.WARNING,  # WARNING because we can continue without charts
                title="Weekly Report - Chart Generation Error",
                details={
                    "channel": channel_name,
                    "period": f"{stats.start_date} to {stats.end_date}",
                    "error": str(e),
                },
            )
        chart_paths = {}

    # Capture Kibana dashboard if available
    kibana_screenshot = None
    if kibana_capture is not None and not dry_run:
        try:
            dashboard_path = str(reports_dir / "kibana_weekly_dashboard.png")
            kibana_capture.capture_dashboard(weekly_dashboard_id, dashboard_path, time_range="7d", wait_for_render=10)
            kibana_screenshot = dashboard_path
            logger.info(f"Captured Kibana dashboard to {kibana_screenshot}")
        except Exception as e:
            error_msg = f"Failed to capture Kibana dashboard: {e}"
            logger.error(error_msg)

            alert(
                message=error_msg,
                level=AlertLevel.WARNING,
                title="Weekly Report - Kibana Capture Error",
                details={
                    "channel": channel_name,
                    "period": f"{stats.start_date} to {stats.end_date}",
                    "dashboard_id": weekly_dashboard_id,
                    "error": str(e),
                },
            )

    payload = build_weekly_report_payload(stats, chart_paths, kibana_screenshot)

    # Display report
    logger.info(f"Weekly Report:\n{payload.formatted_text}")

    # Post to Slack if not dry run
    if not dry_run and client is not None:
        try:
            client.post_message_markdown(payload.formatted_text)

            for item in payload.upload_plan:
                client.upload_file(item.path, item.title)

            logger.info("Posted weekly report to Slack")
        except Exception as e:
            error_msg = f"Failed to post weekly report: {e}"
            logger.error(error_msg)

            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Weekly Report - Posting Error",
                details={
                    "channel": channel_name,
                    "period": f"{stats.start_date} to {stats.end_date}",
                    "error": str(e),
                },
            )
    else:
        logger.info("Dry run - not posting to Slack")
