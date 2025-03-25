"""
Daily Analysis
Provides functionality for daily analysis of Slack messages
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from src.es_client.client import ElasticsearchClient
from src.es_client.query import (
    bool_query, date_range_query, match_query, term_query, terms_query,
    build_aggregation_query, terms_aggregation, date_histogram_aggregation
)
from src.utils.date_utils import get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_daily_stats(
    channel_name: str,
    target_date: Optional[datetime] = None,
    es_client: Optional[ElasticsearchClient] = None
) -> Dict[str, Any]:
    """
    Get daily statistics for a channel
    
    Args:
        channel_name: Channel name
        target_date: Target date (default: yesterday)
        es_client: ElasticsearchClient instance (default: create new instance)
        
    Returns:
        Dict[str, Any]: Daily statistics
    """
    # Set target_date to yesterday if not specified
    if target_date is None:
        current_time = get_current_time()
        target_date = current_time - timedelta(days=1)
    
    # Set start and end date
    start_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    logger.info(f"Getting daily stats for {channel_name} on {target_date.strftime('%Y-%m-%d')}")
    
    # Initialize Elasticsearch client if not provided
    if es_client is None:
        es_client = ElasticsearchClient()
    
    # Get index name
    index_name = f"slack-{channel_name.lower()}"
    
    # Get message count
    message_count = get_message_count(es_client, index_name, start_date, end_date)
    
    # Get reaction count
    reaction_count = get_reaction_count(es_client, index_name, start_date, end_date)
    
    # Get hourly distribution
    hourly_distribution = get_hourly_distribution(es_client, index_name, start_date, end_date)
    
    # Get top reactions
    top_reactions = get_top_reactions(es_client, index_name, start_date, end_date)
    
    # Get user stats
    user_stats = get_user_stats(es_client, index_name, start_date, end_date)
    
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "message_count": message_count,
        "reaction_count": reaction_count,
        "hourly_distribution": hourly_distribution,
        "top_reactions": top_reactions,
        "user_stats": user_stats
    }


def get_message_count(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: datetime,
    end_date: datetime
) -> int:
    """
    Get message count for a date range
    
    Args:
        es_client: ElasticsearchClient instance
        index_name: Index name
        start_date: Start date
        end_date: End date
        
    Returns:
        int: Message count
    """
    # Create query
    query = bool_query(
        filter_=[
            date_range_query("timestamp", start_date, end_date)
        ]
    )
    
    # Execute query
    try:
        result = es_client.search(
            index_name=index_name,
            query=query,
            size=0
        )
        
        return result.get("hits", {}).get("total", {}).get("value", 0)
    except Exception as e:
        logger.error(f"Failed to get message count: {e}")
        return 0


def get_reaction_count(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: datetime,
    end_date: datetime
) -> int:
    """
    Get reaction count for a date range
    
    Args:
        es_client: ElasticsearchClient instance
        index_name: Index name
        start_date: Start date
        end_date: End date
        
    Returns:
        int: Reaction count
    """
    # Create aggregation query
    aggs = {
        "reaction_count": {
            "sum": {
                "field": "reactions.count"
            }
        }
    }
    
    query = build_aggregation_query(
        aggs=aggs,
        query_parts=[
            date_range_query("timestamp", start_date, end_date)
        ]
    )
    
    # Execute query
    try:
        result = es_client.search(
            index_name=index_name,
            query=query,
            size=0
        )
        
        return int(result.get("aggregations", {}).get("reaction_count", {}).get("value", 0))
    except Exception as e:
        logger.error(f"Failed to get reaction count: {e}")
        return 0


def get_hourly_distribution(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: datetime,
    end_date: datetime
) -> Dict[int, int]:
    """
    Get hourly distribution of messages
    
    Args:
        es_client: ElasticsearchClient instance
        index_name: Index name
        start_date: Start date
        end_date: End date
        
    Returns:
        Dict[int, int]: Hourly distribution (hour -> count)
    """
    # Create aggregation query
    aggs = {
        "hourly": {
            "terms": {
                "field": "hour_of_day",
                "size": 24
            }
        }
    }
    
    query = build_aggregation_query(
        aggs=aggs,
        query_parts=[
            date_range_query("timestamp", start_date, end_date)
        ]
    )
    
    # Execute query
    try:
        result = es_client.search(
            index_name=index_name,
            query=query,
            size=0
        )
        
        # Process results
        hourly_distribution = {}
        for bucket in result.get("aggregations", {}).get("hourly", {}).get("buckets", []):
            hour = bucket.get("key")
            count = bucket.get("doc_count", 0)
            hourly_distribution[hour] = count
        
        # Fill in missing hours
        for hour in range(24):
            if hour not in hourly_distribution:
                hourly_distribution[hour] = 0
        
        return dict(sorted(hourly_distribution.items()))
    except Exception as e:
        logger.error(f"Failed to get hourly distribution: {e}")
        return {hour: 0 for hour in range(24)}


def get_top_reactions(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get top reactions
    
    Args:
        es_client: ElasticsearchClient instance
        index_name: Index name
        start_date: Start date
        end_date: End date
        limit: Number of top reactions to return
        
    Returns:
        List[Dict[str, Any]]: Top reactions
    """
    # Create aggregation query
    aggs = {
        "reactions": {
            "nested": {
                "path": "reactions"
            },
            "aggs": {
                "reaction_names": {
                    "terms": {
                        "field": "reactions.name",
                        "size": limit
                    }
                }
            }
        }
    }
    
    query = build_aggregation_query(
        aggs=aggs,
        query_parts=[
            date_range_query("timestamp", start_date, end_date)
        ]
    )
    
    # Execute query
    try:
        result = es_client.search(
            index_name=index_name,
            query=query,
            size=0
        )
        
        # Process results
        top_reactions = []
        for bucket in result.get("aggregations", {}).get("reactions", {}).get("reaction_names", {}).get("buckets", []):
            name = bucket.get("key")
            count = bucket.get("doc_count", 0)
            top_reactions.append({
                "name": name,
                "count": count
            })
        
        return top_reactions
    except Exception as e:
        logger.error(f"Failed to get top reactions: {e}")
        return []


def get_user_stats(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get user statistics
    
    Args:
        es_client: ElasticsearchClient instance
        index_name: Index name
        start_date: Start date
        end_date: End date
        limit: Number of top users to return
        
    Returns:
        List[Dict[str, Any]]: User statistics
    """
    # Create aggregation query
    aggs = {
        "users": {
            "terms": {
                "field": "username",
                "size": limit
            }
        }
    }
    
    query = build_aggregation_query(
        aggs=aggs,
        query_parts=[
            date_range_query("timestamp", start_date, end_date)
        ]
    )
    
    # Execute query
    try:
        result = es_client.search(
            index_name=index_name,
            query=query,
            size=0
        )
        
        # Process results
        user_stats = []
        for bucket in result.get("aggregations", {}).get("users", {}).get("buckets", []):
            username = bucket.get("key")
            count = bucket.get("doc_count", 0)
            user_stats.append({
                "username": username,
                "message_count": count
            })
        
        return user_stats
    except Exception as e:
        logger.error(f"Failed to get user stats: {e}")
        return []