"""
Provides functionality for generating daily reports.
"""

from datetime import datetime
from typing import Optional

from src.analysis.daily_pipeline import (
    build_daily_hourly_histogram_query,
    build_daily_message_count_query,
    build_daily_reaction_sum_query,
    build_daily_stats,
    day_bounds_strings,
    parse_hourly_buckets_to_counts,
    parse_reaction_sum_value,
    parse_search_total_hits,
)
from src.analysis.types import DailyStats
from src.es_client.client import ElasticsearchClient
from src.es_client.index import get_index_name


def get_daily_stats(
    channel_name: str,
    date: datetime,
    es_client: ElasticsearchClient,
    *,
    fallback_channel_name: Optional[str] = None,
) -> DailyStats:
    """
    Get daily statistics for a specific channel and date (ES I/O orchestration).

    Args:
        channel_name: Channel name
        date: Date to get stats for
        es_client: Elasticsearch client (caller must construct)

    Returns:
        Daily statistics
    """
    if not channel_name and fallback_channel_name:
        channel_name = fallback_channel_name

    date_str, _ = day_bounds_strings(date)
    index_name = get_index_name(channel_name)

    msg_resp = es_client.search(index_name, build_daily_message_count_query(date))
    reaction_resp = es_client.search(index_name, build_daily_reaction_sum_query(date))
    hourly_resp = es_client.search(index_name, build_daily_hourly_histogram_query(date))

    message_count = parse_search_total_hits(msg_resp)
    reaction_count = parse_reaction_sum_value(reaction_resp)
    hourly_counts = parse_hourly_buckets_to_counts(hourly_resp)

    return build_daily_stats(date_str, message_count, reaction_count, hourly_counts)
