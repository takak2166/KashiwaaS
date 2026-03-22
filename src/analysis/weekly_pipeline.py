"""
Pure functions: weekly date range, aggregation from daily rows, top-post query and parsing.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from src.analysis.types import DailyStats


def week_bounds_from_end_date(end_date: datetime) -> Tuple[datetime, datetime, str, str]:
    """
    Seven-day window ending on end_date: start = end - 6 days.
    Returns (start_date, end_date, start_date_str, end_date_str).
    """
    start_date = end_date - timedelta(days=6)
    return (
        start_date,
        end_date,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )


def aggregate_weekly_from_daily_stats(daily_stats: List[DailyStats]) -> Tuple[int, int, List[int]]:
    """Sum messages/reactions and concatenate hourly arrays from daily stats."""
    total_messages = sum(s.message_count for s in daily_stats)
    total_reactions = sum(s.reaction_count for s in daily_stats)
    hourly_flat: List[int] = []
    for s in daily_stats:
        hourly_flat.extend(s.hourly_message_counts)
    return total_messages, total_reactions, hourly_flat


def build_top_posts_search_body(start_date: str, end_date: str, size: int = 100) -> Dict[str, Any]:
    """ES query: messages with reactions in date range (inclusive by day string)."""
    return {
        "query": {
            "bool": {
                "must": [
                    {"range": {"timestamp": {"gte": start_date, "lte": end_date}}},
                    {
                        "nested": {
                            "path": "reactions",
                            "query": {"exists": {"field": "reactions"}},
                        }
                    },
                ]
            }
        },
        "aggs": {
            "total_reactions": {
                "nested": {"path": "reactions"},
                "aggs": {"sum": {"sum": {"field": "reactions.count"}}},
            }
        },
        "size": size,
    }


def _message_ts_for_slack_link(source: Dict[str, Any]) -> str:
    """Derive Slack permalink ts fragment from ES _source (no I/O)."""
    thread_ts = source.get("thread_ts", "") or ""
    ts = source.get("ts", "") or ""
    message_ts = thread_ts if thread_ts else ts
    if not message_ts:
        timestamp = source.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                message_ts = f"{int(dt.timestamp())}{dt.microsecond:06d}"
            except (ValueError, AttributeError, TypeError):
                message_ts = ""
    if message_ts:
        message_ts = message_ts.replace(".", "")
    return message_ts


def map_top_post_hits(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map ES hits list to top-post row dicts (unsorted)."""
    return [es_hit_to_top_post_row(hit) for hit in hits]


def es_hit_to_top_post_row(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Map one ES hit to a top-post row dict."""
    source = hit.get("_source", {})
    reactions = source.get("reactions", [])
    total_reactions = sum(r.get("count", 0) for r in reactions)
    text = source.get("text", "")
    if "\n" in text:
        text = text.split("\n")[0] + "..."

    channel_id = source.get("channel_id", "")
    message_ts = _message_ts_for_slack_link(source)
    slack_link = f"https://slack.com/archives/{channel_id}/p{message_ts}"

    return {
        "text": text,
        "slack_link": slack_link,
        "user": source.get("user", "unknown"),
        "reaction_count": total_reactions,
        "reactions": reactions,
    }


def sort_and_limit_top_posts(posts: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Sort by reaction_count descending and take first `limit`."""
    sorted_posts = sorted(posts, key=lambda x: x["reaction_count"], reverse=True)
    return sorted_posts[:limit]
