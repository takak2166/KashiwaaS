"""
Provides functionality for formatting messages.
"""

from typing import Any, Dict, List

from src.analysis.types import DailyStats, WeeklyStats
from src.utils.logger import get_logger

logger = get_logger(__name__)


def format_daily_report(stats: DailyStats) -> str:
    """
    Format daily report message

    Args:
        stats: Daily statistics

    Returns:
        str: Formatted message
    """
    message = f"Daily Report for {stats.date}\n\n"
    message += f"Total Messages: {stats.message_count}\n"
    message += f"Total Reactions: {stats.reaction_count}\n\n"

    return message


def format_weekly_report(stats: WeeklyStats) -> str:
    """
    Format weekly report message

    Args:
        stats: Weekly statistics

    Returns:
        str: Formatted message
    """
    message = f"Weekly Report ({stats.start_date} to {stats.end_date})\n\n"
    message += f"Total Messages: {stats.message_count}\n"
    message += f"Total Reactions: {stats.reaction_count}\n\n"

    if stats.top_posts:
        message += "\nTop Posts:\n"
        message += format_top_posts_with_reactions(list(stats.top_posts))

    return message


def format_chart_title(chart_type: str, date_str: str, is_weekly: bool = False) -> str:
    """
    Format chart title for file uploads

    Args:
        chart_type: Type of chart
        date_str: Date string
        is_weekly: Whether this is a weekly chart

    Returns:
        str: Formatted chart title
    """
    period_type = "Weekly" if is_weekly else "Daily"
    return f"{period_type} {chart_type.capitalize()} Chart - {date_str}"


def format_dashboard_title(date_str: str, is_weekly: bool = False) -> str:
    """
    Format dashboard title for file uploads

    Args:
        date_str: Date string
        is_weekly: Whether this is a weekly dashboard

    Returns:
        str: Formatted dashboard title
    """
    return f"Kibana Dashboard - {date_str}"


def format_top_posts_with_reactions(posts: List[Dict[str, Any]]) -> str:
    """
    Format top posts with most reactions

    Args:
        posts: List of posts with reactions

    Returns:
        str: Formatted string
    """
    if not posts:
        return "No posts with reactions found."

    formatted_posts = []
    for i, post in enumerate(posts, 1):
        total_reactions = sum(r["count"] for r in post["reactions"])

        message_text = post["text"]
        if len(message_text) > 100:
            message_text = message_text[:100] + "..."

        slack_link = post["slack_link"]

        formatted_post = f"{i}. <{slack_link}|{message_text}> ({total_reactions} reactions)"
        formatted_posts.append(formatted_post)

    return "\n\n".join(formatted_posts)
