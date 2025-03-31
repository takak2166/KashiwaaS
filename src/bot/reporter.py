"""
Reporter Module
Provides functionality for generating and posting reports to Slack
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.analysis.daily import get_daily_stats
from src.analysis.visualization import create_daily_report_charts, create_weekly_report_charts
from src.bot.alerter import alert, AlertLevel
from src.bot.formatter import (
    format_daily_report, 
    format_weekly_report, 
    format_chart_title, 
    format_dashboard_title
)
from src.kibana.capture import KibanaCapture
from src.kibana.dashboard import KibanaDashboard
from src.slack.client import SlackClient
from src.utils.date_utils import get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
        error_msg = f"Failed to get channel info: {e}"
        logger.error(error_msg)
        
        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Daily Report - Channel Info Error",
            details={
                "channel_id": client.channel_id,
                "error": str(e)
            }
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
            details={
                "channel": channel_name,
                "date": target_date.strftime('%Y-%m-%d'),
                "error": str(e)
            }
        )
        return
    
    # Create output directory
    reports_dir = Path("reports") / channel_name
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate charts
    try:
        chart_paths = create_daily_report_charts(stats, str(reports_dir))
        logger.info(f"Generated charts: {chart_paths}")
    except Exception as e:
        error_msg = f"Failed to generate charts: {e}"
        logger.error(error_msg)
        
        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.WARNING,  # WARNING because we can continue without charts
            title="Daily Report - Chart Generation Error",
            details={
                "channel": channel_name,
                "date": target_date.strftime('%Y-%m-%d'),
                "error": str(e)
            }
        )
        chart_paths = {}
    
    # Capture Kibana dashboard if available
    kibana_screenshot = None
    try:
        kibana = KibanaDashboard()
        kibana_capture = KibanaCapture()
        
        # ダッシュボードIDを変数として定義
        DAILY_DASHBOARD_ID = os.getenv("KIBANA_DAILY_DASHBOARD_ID", "slack-daily-dashboard")
        
        # Capture dashboard
        dashboard_path = str(reports_dir / f"kibana_daily_{stats['date']}.png")
        kibana_capture.capture_dashboard(
            DAILY_DASHBOARD_ID,
            dashboard_path,
            time_range="1d",
            wait_for_render=10
        )
        kibana_screenshot = dashboard_path
        logger.info(f"Captured Kibana dashboard to {kibana_screenshot}")
    except Exception as e:
        error_msg = f"Failed to capture Kibana dashboard: {e}"
        logger.error(error_msg)
        
        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.WARNING,  # WARNING because we can continue without Kibana screenshot
            title="Daily Report - Kibana Capture Error",
            details={
                "channel": channel_name,
                "date": target_date.strftime('%Y-%m-%d'),
                "dashboard_id": os.getenv("KIBANA_DAILY_DASHBOARD_ID", "slack-daily-dashboard"),
                "error": str(e)
            }
        )
    
    # Format report message
    message = format_daily_report(stats)
    
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
                        format_chart_title(chart_type, stats['date']),
                        post_result.get("ts")
                    )
            
            # Upload Kibana screenshot
            if kibana_screenshot:
                client.upload_file(
                    kibana_screenshot,
                    format_dashboard_title(stats['date']),
                    post_result.get("ts")
                )
            
            logger.info("Posted daily report to Slack")
        except Exception as e:
            error_msg = f"Failed to post daily report: {e}"
            logger.error(error_msg)
            
            # Send alert
            alert(
                message=error_msg,
                level=AlertLevel.ERROR,
                title="Daily Report - Posting Error",
                details={
                    "channel": channel_name,
                    "date": target_date.strftime('%Y-%m-%d'),
                    "error": str(e)
                }
            )
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
        error_msg = f"Failed to get channel info: {e}"
        logger.error(error_msg)
        
        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.ERROR,
            title="Weekly Report - Channel Info Error",
            details={
                "channel_id": client.channel_id,
                "error": str(e)
            }
        )
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
    error_dates = []  # Track dates with errors
    current_date = start_date
    
    while current_date <= end_date:
        try:
            stats = get_daily_stats(channel_name, current_date)
            daily_stats.append(stats)
            logger.info(f"Got daily stats for {current_date.strftime('%Y-%m-%d')}: {stats['message_count']} messages")
        except Exception as e:
            error_msg = f"Failed to get daily stats for {current_date.strftime('%Y-%m-%d')}: {e}"
            logger.error(error_msg)
            # Add to error dates list instead of sending alert immediately
            error_dates.append(current_date.strftime('%Y-%m-%d'))
        
        current_date += timedelta(days=1)
    
    # Send a single consolidated alert if there were any errors
    if error_dates:
        alert(
            message=f"Failed to get daily stats for {len(error_dates)} day(s) in weekly report",
            level=AlertLevel.WARNING,  # WARNING because we can continue with partial data
            title="Weekly Report - Daily Stats Error",
            details={
                "channel": channel_name,
                "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "dates_with_errors": ", ".join(error_dates),
                "error": "Multiple errors occurred while fetching daily stats"
            }
        )
    
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
        error_msg = f"Failed to generate charts: {e}"
        logger.error(error_msg)
        
        # Send alert
        alert(
            message=error_msg,
            level=AlertLevel.WARNING,  # WARNING because we can continue without charts
            title="Weekly Report - Chart Generation Error",
            details={
                "channel": channel_name,
                "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "error": str(e)
            }
        )
        chart_paths = {}
    
    # Capture Kibana dashboard if available
    kibana_screenshot = None
    try:
        kibana = KibanaDashboard()
        kibana_capture = KibanaCapture()
        
        # ダッシュボードIDを変数として定義
        WEEKLY_DASHBOARD_ID = os.getenv("KIBANA_WEEKLY_DASHBOARD_ID", "slack-weekly-dashboard")
        
        # Capture dashboard
        dashboard_path = str(reports_dir / f"kibana_weekly_{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}.png")
        kibana_capture.capture_dashboard(
            WEEKLY_DASHBOARD_ID,
            dashboard_path,
            time_range="7d",
            wait_for_render=10
        )
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
                "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "dashboard_id": os.getenv("KIBANA_WEEKLY_DASHBOARD_ID", "slack-weekly-dashboard"),
                "error": str(e)
            }
        )
    
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
    message = format_weekly_report(
        daily_stats=daily_stats,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        total_messages=total_messages,
        total_reactions=total_reactions,
        top_users=top_users
    )
    
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
                        format_chart_title(
                            chart_type, 
                            f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                            is_weekly=True
                        )
                    )
            
            # Upload Kibana screenshot
            if kibana_screenshot:
                client.upload_file(
                    kibana_screenshot,
                    format_dashboard_title(
                        f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                        is_weekly=True
                    )
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
                    "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                    "error": str(e)
                }
            )
    else:
        logger.info("Dry run - not posting to Slack")