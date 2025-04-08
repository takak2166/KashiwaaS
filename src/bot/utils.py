"""
Utility functions for Slack bot
"""
from typing import Optional


def create_slack_link(channel_name: str, message_ts: str) -> str:
    """
    Create a Slack link for a message
    
    Args:
        channel_name: Channel name
        message_ts: Message timestamp
        
    Returns:
        str: Slack message link
    """
    # Format timestamp (remove decimal point if present)
    formatted_ts = message_ts.replace(".", "")
    
    # Create Slack link
    return f"https://slack.com/archives/{channel_name}/p{formatted_ts}" 