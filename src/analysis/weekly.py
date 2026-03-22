"""
Weekly Analysis Module
Provides functionality for generating weekly reports
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.analysis.daily import get_daily_stats
from src.analysis.weekly_pipeline import (
    aggregate_weekly_from_daily_stats,
    build_top_posts_search_body,
    map_top_post_hits,
    sort_and_limit_top_posts,
    week_bounds_from_end_date,
)
from src.es_client.client import ElasticsearchClient
from src.es_client.index import get_index_name
from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_weekly_stats(
    channel_name: str,
    es_client: ElasticsearchClient,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get weekly statistics

    Args:
        channel_name: Channel name
        es_client: Elasticsearch client (caller must construct)
        end_date: End date (default: yesterday)

    Returns:
        Dict[str, Any]: Weekly statistics
    """
    if end_date is None:
        end_date = datetime.now() - timedelta(days=1)

    start_date, end_date, start_date_str, end_date_str = week_bounds_from_end_date(end_date)

    if not channel_name and config:
        channel_name = config.slack.channel_name
    index_name = get_index_name(channel_name)

    daily_stats: List[Dict[str, Any]] = []
    error_dates: List[str] = []
    current_date = start_date

    while current_date <= end_date:
        try:
            stats = get_daily_stats(channel_name, current_date, es_client)
            daily_stats.append(stats)
            logger.info(
                f"Got daily stats for {current_date.strftime('%Y-%m-%d')}: " f"{stats['message_count']} messages"
            )
        except Exception as e:
            error_msg = f"Failed to get daily stats for {current_date.strftime('%Y-%m-%d')}: {e}"
            logger.error(error_msg)
            error_dates.append(current_date.strftime("%Y-%m-%d"))

        current_date += timedelta(days=1)

    if not daily_stats:
        logger.error("No data available for the specified period")
        return {}

    total_messages, total_reactions, hourly_flat = aggregate_weekly_from_daily_stats(daily_stats)

    top_posts = get_top_posts_with_reactions(es_client, index_name, start_date_str, end_date_str)

    return {
        "start_date": start_date_str,
        "end_date": end_date_str,
        "message_count": total_messages,
        "reaction_count": total_reactions,
        "top_posts": top_posts,
        "hourly_message_counts": hourly_flat,
        "error_dates": error_dates,
        "daily_stats": daily_stats,
    }


def get_top_posts_with_reactions(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: str,
    end_date: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Get top posts with most reactions

    Args:
        es_client: Elasticsearch client
        index_name: Index name
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        limit: Number of posts to return

    Returns:
        List[Dict[str, Any]]: List of top posts with reactions
    """
    query = build_top_posts_search_body(start_date, end_date, size=100)
    response = es_client.search(index_name, query)
    hits = response.get("hits", {}).get("hits", [])
    rows = map_top_post_hits(hits)
    return sort_and_limit_top_posts(rows, limit)
