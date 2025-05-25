"""
Elasticsearch Index Management
Provides functions and templates for managing Elasticsearch indices
"""

from typing import Any, Dict

# Default index template for Slack messages
SLACK_INDEX_TEMPLATE = {
    "index_patterns": ["slack-*"],
    "priority": 100,
    "version": 1,
    "_meta": {"description": "Template for Slack messages"},
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "kuromoji_analyzer": {
                        "type": "custom",
                        "tokenizer": "kuromoji_tokenizer",
                        "filter": [
                            "kuromoji_baseform",
                            "lowercase",
                            "ja_stop",
                            "kuromoji_part_of_speech",
                        ],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "timestamp": {"type": "date"},
                "channel_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "username": {"type": "keyword"},
                "text": {
                    "type": "text",
                    "analyzer": "kuromoji_analyzer",
                    "fielddata": True,
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "thread_ts": {"type": "keyword"},
                "reply_count": {"type": "integer"},
                "reactions": {
                    "type": "nested",
                    "properties": {
                        "name": {"type": "keyword"},
                        "count": {"type": "integer"},
                        "users": {"type": "keyword"},
                    },
                },
                "mentions": {"type": "keyword"},
                "attachments": {
                    "type": "nested",
                    "properties": {
                        "type": {"type": "keyword"},
                        "size": {"type": "long"},
                        "url": {"type": "keyword"},
                    },
                },
                "is_weekend": {"type": "boolean"},
                "hour_of_day": {"type": "integer"},
                "day_of_week": {"type": "integer"},
            }
        },
    },
}


def get_index_name(channel_name: str) -> str:
    """
    Generate index name from channel name

    Args:
        channel_name: Slack channel name

    Returns:
        str: Formatted index name
    """
    # Remove special characters and convert to lowercase
    clean_name = "".join(c if c.isalnum() else "-" for c in channel_name.lower())
    return f"slack-{clean_name}"


def get_slack_template() -> Dict[str, Any]:
    """
    Get Slack messages index template

    Returns:
        Dict[str, Any]: Template definition
    """
    return SLACK_INDEX_TEMPLATE
