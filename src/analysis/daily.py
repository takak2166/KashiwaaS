"""
Provides functionality for generating daily reports.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.es_client.client import ElasticsearchClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_daily_stats(
    channel_name: str, date: datetime, es_client: Optional[ElasticsearchClient] = None
) -> Dict[str, Any]:
    """
    Get daily statistics for a specific channel and date.

    Args:
        channel_name: Channel name
        date: Date to get stats for
        es_client: Elasticsearch client (optional)

    Returns:
        Dict[str, Any]: Daily statistics
    """
    # Initialize Elasticsearch client if not provided
    if es_client is None:
        es_client = ElasticsearchClient()

    # Format date for Elasticsearch
    date_str = date.strftime("%Y-%m-%d")

    # Get index name
    index_name = f"slack-{channel_name}"

    # Get total messages and reactions
    message_count = es_client.search(
        index_name,
        {
            "size": 0,
            "query": {
                "range": {
                    "timestamp": {
                        "gte": date_str,
                        "lt": (date + timedelta(days=1)).strftime("%Y-%m-%d"),
                        "time_zone": "+09:00",
                    }
                }
            },
        },
    )["hits"]["total"]["value"]

    reaction_count = es_client.search(
        index_name,
        {
            "size": 0,
            "query": {
                "range": {
                    "timestamp": {
                        "gte": date_str,
                        "lt": (date + timedelta(days=1)).strftime("%Y-%m-%d"),
                        "time_zone": "+09:00",
                    }
                }
            },
            "aggs": {
                "reactions_nested": {
                    "nested": {"path": "reactions"},
                    "aggs": {"total_count": {"sum": {"field": "reactions.count"}}},
                }
            },
        },
    )["aggregations"]["reactions_nested"]["total_count"]["value"]

    # Get hourly message counts
    result = es_client.search(
        index_name,
        {
            "size": 0,
            "query": {
                "range": {
                    "timestamp": {
                        "gte": date_str,
                        "lt": (date + timedelta(days=1)).strftime("%Y-%m-%d"),
                        "time_zone": "+09:00",
                    }
                }
            },
            "aggs": {
                "hourly": {
                    "date_histogram": {
                        "field": "timestamp",
                        "calendar_interval": "hour",
                        "format": "yyyy-MM-dd HH:mm:ss",
                        "time_zone": "Asia/Tokyo",
                    }
                }
            },
        },
    )

    # Initialize hourly counts
    hourly_counts = [0] * 24

    # Fill in the counts from the aggregation
    for bucket in result.get("aggregations", {}).get("hourly", {}).get("buckets", []):
        hour = int(bucket.get("key_as_string", "").split(" ")[1].split(":")[0])
        count = bucket.get("doc_count", 0)
        hourly_counts[hour] = count

    return {
        "date": date_str,
        "message_count": message_count,
        "reaction_count": int(reaction_count),
        "hourly_message_counts": hourly_counts,
    }
