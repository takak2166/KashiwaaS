"""
Pure data prep for charts (no matplotlib/plotly).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple


def build_weekly_two_hour_series(start_date: datetime, hourly_message_counts: List[int]) -> Tuple[List[int], List[str]]:
    """
    Aggregate 168 hourly counts into 2-hour buckets with ISO-like x labels.
    """
    two_hour_counts: List[int] = []
    two_hour_labels: List[str] = []
    for day in range(7):
        current_date = start_date + timedelta(days=day)
        for hour in range(0, 24, 2):
            idx = day * 24 + hour
            count = sum(hourly_message_counts[idx : idx + 2])
            two_hour_counts.append(count)
            label = f"{current_date.strftime('%Y-%m-%d')} {hour:02d}:00"
            two_hour_labels.append(label)
    return two_hour_counts, two_hour_labels


def aggregate_reaction_totals_from_top_posts(top_posts: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """Sum reaction counts by emoji name across top post rows."""
    reaction_counts: Dict[str, int] = {}
    for post in top_posts:
        for reaction in post.get("reactions", []):
            name = reaction["name"]
            count = reaction["count"]
            reaction_counts[name] = reaction_counts.get(name, 0) + count
    top_reactions = [
        {"name": name, "count": count}
        for name, count in sorted(reaction_counts.items(), key=lambda x: x[1], reverse=True)
    ][:limit]
    return top_reactions


def group_hourly_dict(hourly_data: Dict[int, int], group_by: int) -> Tuple[List[int], List[int], List[str]]:
    """
    From hour->count map, build grouped counts, bucket start hours, and x tick labels.
    """
    if group_by > 1:
        grouped_data: Dict[int, int] = {}
        for hour in range(0, 24, group_by):
            group_count = sum(hourly_data.get(h, 0) for h in range(hour, min(hour + group_by, 24)))
            grouped_data[hour] = group_count

        hours = list(range(0, 24, group_by))
        counts = [grouped_data.get(hour, 0) for hour in hours]
        labels = [f"{h:02d}:00-{(h + group_by) % 24:02d}:00" for h in hours]
    else:
        hours = list(range(24))
        counts = [hourly_data.get(hour, 0) for hour in hours]
        labels = [f"{h:02d}:00" for h in hours]
    return counts, hours, labels
