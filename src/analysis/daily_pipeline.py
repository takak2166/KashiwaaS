"""
Pure functions: daily Elasticsearch query bodies and response parsing.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from src.analysis.types import DailyStats
from src.es_client.query import timestamp_range_query


def day_bounds_strings(date: datetime) -> tuple[str, str]:
    """Inclusive date string and exclusive next-day string for daily range queries."""
    date_str = date.strftime("%Y-%m-%d")
    next_day_str = (date + timedelta(days=1)).strftime("%Y-%m-%d")
    return date_str, next_day_str


def _daily_timestamp_query_clause(date: datetime) -> Dict[str, Any]:
    """Single-day JST calendar window as an ES query clause."""
    date_str, next_day_str = day_bounds_strings(date)
    return timestamp_range_query("timestamp", gte=date_str, lt=next_day_str, time_zone="+09:00")


def build_daily_message_count_query(date: datetime) -> Dict[str, Any]:
    """ES search body: count messages in [date, next day)."""
    return {
        "size": 0,
        "query": _daily_timestamp_query_clause(date),
    }


def build_daily_reaction_sum_query(date: datetime) -> Dict[str, Any]:
    """ES search body: sum nested reaction counts for one calendar day (JST range)."""
    return {
        "size": 0,
        "query": _daily_timestamp_query_clause(date),
        "aggs": {
            "reactions_nested": {
                "nested": {"path": "reactions"},
                "aggs": {"total_count": {"sum": {"field": "reactions.count"}}},
            }
        },
    }


def build_daily_hourly_histogram_query(date: datetime) -> Dict[str, Any]:
    """ES search body: hourly doc counts for one calendar day (JST)."""
    return {
        "size": 0,
        "query": _daily_timestamp_query_clause(date),
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
    }


def parse_search_total_hits(response: Dict[str, Any]) -> int:
    """Extract total hit count from ES search response (size=0 count)."""
    total = response.get("hits", {}).get("total", 0)
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total or 0)


def parse_reaction_sum_value(response: Dict[str, Any]) -> int:
    """Extract nested sum of reactions.count from aggregation response."""
    val = response.get("aggregations", {}).get("reactions_nested", {}).get("total_count", {}).get("value", 0)
    return int(val)


def parse_hourly_buckets_to_counts(response: Dict[str, Any]) -> List[int]:
    """Fill a 24-length list from date_histogram buckets (key_as_string JST)."""
    hourly_counts = [0] * 24
    for bucket in response.get("aggregations", {}).get("hourly", {}).get("buckets", []):
        key_as_string = bucket.get("key_as_string", "")
        try:
            hour = int(key_as_string.split(" ")[1].split(":")[0])
        except (IndexError, ValueError):
            continue
        hourly_counts[hour] = bucket.get("doc_count", 0)
    return hourly_counts


def build_daily_stats(
    date_str: str,
    message_count: int,
    reaction_count: int,
    hourly_message_counts: List[int],
) -> DailyStats:
    """Assemble immutable daily stats for formatters and weekly aggregation."""
    return DailyStats(
        date=date_str,
        message_count=message_count,
        reaction_count=reaction_count,
        hourly_message_counts=tuple(hourly_message_counts),
    )
