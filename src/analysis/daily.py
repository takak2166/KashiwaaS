"""
Provides functionality for generating daily reports.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
                        "time_zone": "+09:00"
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
                        "time_zone": "+09:00"
                    }
                }
            },
            "aggs": {
                "reactions_nested": {
                    "nested": {
                        "path": "reactions"
                    },
                    "aggs": {
                        "total_count": {
                            "sum": {
                                "field": "reactions.count"
                            }
                        }
                    },
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
                        "time_zone": "+09:00"
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

    # Get user stats
    user_stats = get_user_stats(es_client, index_name, date_str, (date + timedelta(days=1)).strftime("%Y-%m-%d"))

    return {
        "date": date_str,
        "message_count": message_count,
        "reaction_count": int(reaction_count),
        "user_stats": user_stats,
        "hourly_message_counts": hourly_counts,
    }


def get_user_stats(
    es_client: ElasticsearchClient, index_name: str, start_date: str, end_date: str
) -> List[Dict[str, Any]]:
    """
    Get user statistics for the day

    Args:
        es_client: Elasticsearch client
        index_name: Index name
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        List[Dict[str, Any]]: List of user statistics
    """
    # Query to get user message counts
    query = {
        "size": 0,
        "query": {"range": {"timestamp": {"gte": start_date, "lt": end_date}}},
        "aggs": {"users": {"terms": {"field": "user", "size": 10, "order": {"_count": "desc"}}}},
    }

    # Execute search
    response = es_client.search(index_name, query)

    # Process results
    user_stats = []
    for bucket in response.get("aggregations", {}).get("users", {}).get("buckets", []):
        user_stats.append(
            {
                "username": bucket.get("key", "unknown"),
                "message_count": bucket.get("doc_count", 0),
            }
        )

    return user_stats
