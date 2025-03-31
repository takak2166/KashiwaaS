"""
Message Formatter Module
Provides functionality for formatting Slack messages
"""
from typing import Dict, List, Any, Optional


def format_daily_report(stats: Dict[str, Any]) -> str:
    """
    Format daily report message
    
    Args:
        stats: Daily statistics
        
    Returns:
        str: Formatted message
    """
    message = f"*Daily Report for {stats['date']}*\n\n"
    message += f"• Total Messages: *{stats['message_count']}*\n"
    message += f"• Total Reactions: *{stats['reaction_count']}*\n\n"
    
    if stats.get('user_stats'):
        message += "*Top Active Users:*\n"
        for user in stats['user_stats'][:5]:
            message += f"• {user['username']}: {user['message_count']} messages\n"
        message += "\n"
    
    if stats.get('top_reactions'):
        message += "*Top Reactions:*\n"
        for reaction in stats['top_reactions'][:5]:
            message += f"• :{reaction['name']}: - {reaction['count']} times\n"
        message += "\n"
    
    return message


def format_weekly_report(
    daily_stats: List[Dict[str, Any]],
    start_date: str,
    end_date: str,
    total_messages: int,
    total_reactions: int,
    top_users: List[Dict[str, Any]]
) -> str:
    """
    Format weekly report message
    
    Args:
        daily_stats: List of daily statistics
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        total_messages: Total message count
        total_reactions: Total reaction count
        top_users: List of top users
        
    Returns:
        str: Formatted message
    """
    message = f"*Weekly Report ({start_date} to {end_date})*\n\n"
    message += f"• Total Messages: *{total_messages}*\n"
    message += f"• Total Reactions: *{total_reactions}*\n"
    message += f"• Daily Average: *{total_messages / len(daily_stats):.1f}* messages\n\n"
    
    if top_users:
        message += "*Top Active Users:*\n"
        for user in top_users[:5]:
            message += f"• {user['username']}: {user['message_count']} messages\n"
        message += "\n"
    
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