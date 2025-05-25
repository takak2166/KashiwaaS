"""
Slack Message Data Model
Provides data classes for handling message data retrieved from the Slack API
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.date_utils import (
    convert_from_timestamp,
    get_day_of_week,
    get_hour_of_day,
    is_weekend,
)


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
    def from_slack_data(cls, channel_id: str, message_data: Dict[str, Any]) -> "SlackMessage":
        """
        Create a SlackMessage object from message data retrieved from the Slack API

        Args:
            channel_id: Channel ID
            message_data: Message data retrieved from the Slack API

        Returns:
            SlackMessage: Converted message object
        """
        # Convert timestamp to Python datetime
        ts = message_data.get("ts", "0")
        timestamp = convert_from_timestamp(float(ts))

        # User information
        user_id = message_data.get("user", "unknown")
        username = message_data.get("username", "Unknown User")

        # Thread information
        thread_ts = message_data.get("thread_ts")
        reply_count = message_data.get("reply_count", 0)

        # Reaction information
        reactions = []
        for reaction_data in message_data.get("reactions", []):
            reaction = SlackReaction(
                name=reaction_data.get("name", ""),
                count=reaction_data.get("count", 0),
                users=reaction_data.get("users", []),
            )
            reactions.append(reaction)

        # Extract mention information
        mentions = []
        text = message_data.get("text", "")
        # Extract mentions in <@U12345> format
        import re

        mention_pattern = r"<@([A-Z0-9]+)>"
        mentions = re.findall(mention_pattern, text)

        # Attachment information
        attachments = []
        for file_data in message_data.get("files", []):
            attachment = SlackAttachment(
                type=file_data.get("filetype", "unknown"),
                size=file_data.get("size", 0),
                url=file_data.get("url_private", None),
            )
            attachments.append(attachment)

        return cls(
            channel_id=channel_id,
            ts=ts,
            user_id=user_id,
            username=username,
            text=text,
            timestamp=timestamp,
            is_weekend=is_weekend(timestamp),
            hour_of_day=get_hour_of_day(timestamp),
            day_of_week=get_day_of_week(timestamp),
            thread_ts=thread_ts,
            reply_count=reply_count,
            reactions=reactions,
            mentions=mentions,
            attachments=attachments,
            raw_data=message_data,
        )

    def to_elasticsearch_doc(self) -> Dict[str, Any]:
        """
        Convert data to JSON format as an Elasticsearch document

        Returns:
            Dict[str, Any]: Document that can be stored in Elasticsearch
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "username": self.username,
            "text": self.text,
            "thread_ts": self.thread_ts,
            "reply_count": self.reply_count,
            "reactions": [{"name": r.name, "count": r.count, "users": r.users} for r in self.reactions],
            "mentions": self.mentions,
            "attachments": [{"type": a.type, "size": a.size, "url": a.url} for a in self.attachments],
            "is_weekend": self.is_weekend,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
        }
