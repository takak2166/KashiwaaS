"""
Provides functionality for formatting messages.
"""

from typing import Any, Dict, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


def format_daily_report(stats: Dict[str, Any]) -> str:
    """
    Format daily report message

    Args:
        stats: Daily statistics

    Returns:
        str: Formatted message
    """
    # Format message
    message = f"Daily Report for {stats['date']}\n\n"
    message += f"Total Messages: {stats['message_count']}\n"
    message += f"Total Reactions: {stats['reaction_count']}\n\n"

    # Add top users
    if stats.get("user_stats"):
        message += "Top Users:\n"
        for user in stats["user_stats"][:5]:
            message += f"- {user['username']}: {user['message_count']} messages\n"

    return message


def format_weekly_report(
    stats: Dict[str, Any],
    start_date: str,
    end_date: str,
    total_messages: int,
    total_reactions: int,
    top_users: List[Dict[str, Any]],
    top_posts: List[Dict[str, Any]],
) -> str:
    """
    Format weekly report message

    Args:
        stats: Weekly statistics
        start_date: Start date
        end_date: End date
        total_messages: Total message count
        total_reactions: Total reaction count
        top_users: Top users list
        top_posts: Top posts list

    Returns:
        str: Formatted message
    """
    # Format message
    message = f"Weekly Report ({start_date} to {end_date})\n\n"
    message += f"Total Messages: {total_messages}\n"
    message += f"Total Reactions: {total_reactions}\n\n"

    # Add top users
    if top_users:
        message += "Top Users:\n"
        for user in top_users[:5]:
            message += f"- {user['username']}: {user['message_count']} messages\n"

    # Add top posts
    if top_posts:
        message += "\nTop Posts:\n"
        for post in top_posts[:3]:
            message += f"- {post['text'][:100]}... ({post['reaction_count']} reactions)\n"

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


def format_top_posts_with_reactions(posts: List[Dict[str, Any]], channel_name: str) -> str:
    """
    Format top posts with most reactions

    Args:
        posts: List of posts with reactions
        channel_name: Channel name

    Returns:
        str: Formatted string
    """
    if not posts:
        return "No posts with reactions found."

    formatted_posts = []
    for i, post in enumerate(posts, 1):
        # Calculate total reactions
        total_reactions = sum(r["count"] for r in post["reactions"])

        # Format message text (truncate if too long)
        message_text = post["text"]
        if len(message_text) > 100:
            message_text = message_text[:100] + "..."

        # Use existing slack_link
        slack_link = post["slack_link"]

        # Format post
        formatted_post = f"{i}. {message_text} ({total_reactions} reactions)\n<{slack_link}|Link>"
        formatted_posts.append(formatted_post)

    return "\n\n".join(formatted_posts)
