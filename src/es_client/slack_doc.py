"""
Elasticsearch document shape for Slack messages (storage adapter).
"""

from typing import Any, Dict

from src.slack.message import SlackMessage


def slack_message_to_doc(message: SlackMessage) -> Dict[str, Any]:
    """Map a domain SlackMessage to an Elasticsearch _source document."""
    return {
        "timestamp": message.timestamp.isoformat(),
        "channel_id": message.channel_id,
        "user_id": message.user_id,
        "username": message.username,
        "text": message.text,
        "thread_ts": message.thread_ts,
        "reply_count": message.reply_count,
        "reactions": [{"name": r.name, "count": r.count, "users": r.users} for r in message.reactions],
        "mentions": message.mentions,
        "attachments": [{"type": a.type, "size": a.size, "url": a.url} for a in message.attachments],
        "is_weekend": message.is_weekend,
        "hour_of_day": message.hour_of_day,
        "day_of_week": message.day_of_week,
    }
