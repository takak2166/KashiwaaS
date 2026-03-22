"""
Slack Message Data Model
Provides data classes for handling message data retrieved from the Slack API
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.utils.date_utils import (
    convert_from_timestamp,
    get_day_of_week,
    get_hour_of_day,
    is_weekend,
)

_MENTION_PATTERN = re.compile(r"<@([A-Z0-9]+)>")


@dataclass
class SlackReaction:
    """Slack reaction information"""

    name: str
    count: int
    users: List[str] = field(default_factory=list)


@dataclass
class SlackAttachment:
    """Slack attachment information"""

    type: str
    size: int = 0
    url: Optional[str] = None


@dataclass
class SlackMessage:
    """Slack message information"""

    # Basic information
    channel_id: str
    ts: str  # Timestamp (Slack's unique identifier)
    user_id: str
    username: str
    text: str

    # Time information
    timestamp: datetime  # Python datetime
    is_weekend: bool
    hour_of_day: int
    day_of_week: int

    # Thread information
    thread_ts: Optional[str] = None
    reply_count: int = 0

    # Reactions and attachments
    reactions: List[SlackReaction] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    attachments: List[SlackAttachment] = field(default_factory=list)

    # Original Slack data
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_slack_data(cls, channel_id: str, message_data: Dict[str, Any]) -> SlackMessage:
        """
        Create a SlackMessage object from message data retrieved from the Slack API

        Args:
            channel_id: Channel ID
            message_data: Message data retrieved from the Slack API

        Returns:
            SlackMessage: Converted message object
        """
        return build_slack_message(channel_id, message_data)


def extract_mentions(text: str) -> List[str]:
    """Extract user IDs from Slack mention markup `<@U...>`."""
    return _MENTION_PATTERN.findall(text or "")


def map_reactions(reactions_data: Optional[List[Dict[str, Any]]]) -> List[SlackReaction]:
    """Map Slack API reaction dicts to SlackReaction objects."""
    out: List[SlackReaction] = []
    for reaction_data in reactions_data or []:
        out.append(
            SlackReaction(
                name=reaction_data.get("name", ""),
                count=reaction_data.get("count", 0),
                users=reaction_data.get("users", []),
            )
        )
    return out


def map_attachments(files_data: Optional[List[Dict[str, Any]]]) -> List[SlackAttachment]:
    """Map Slack API file dicts to SlackAttachment objects."""
    out: List[SlackAttachment] = []
    for file_data in files_data or []:
        out.append(
            SlackAttachment(
                type=file_data.get("filetype", "unknown"),
                size=file_data.get("size", 0),
                url=file_data.get("url_private", None),
            )
        )
    return out


def derive_message_time_fields(ts_dt: datetime) -> Tuple[bool, int, int]:
    """Derived calendar fields for analytics: weekend flag, hour, weekday index."""
    return is_weekend(ts_dt), get_hour_of_day(ts_dt), get_day_of_week(ts_dt)


def build_slack_message(channel_id: str, message_data: Dict[str, Any]) -> SlackMessage:
    """Assemble SlackMessage from raw Slack API message dict."""
    ts = message_data.get("ts", "0")
    timestamp = convert_from_timestamp(float(ts))
    user_id = message_data.get("user", "unknown")
    username = message_data.get("username", "Unknown User")
    thread_ts = message_data.get("thread_ts")
    reply_count = message_data.get("reply_count", 0)
    text = message_data.get("text", "")
    mentions = extract_mentions(text)
    reactions = map_reactions(message_data.get("reactions", []))
    attachments = map_attachments(message_data.get("files", []))
    is_wk, hour, dow = derive_message_time_fields(timestamp)

    return SlackMessage(
        channel_id=channel_id,
        ts=ts,
        user_id=user_id,
        username=username,
        text=text,
        timestamp=timestamp,
        is_weekend=is_wk,
        hour_of_day=hour,
        day_of_week=dow,
        thread_ts=thread_ts,
        reply_count=reply_count,
        reactions=reactions,
        mentions=mentions,
        attachments=attachments,
        raw_data=message_data,
    )
