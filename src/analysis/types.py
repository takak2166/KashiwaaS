"""Immutable domain types for analysis / reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass(frozen=True)
class DailyStats:
    """One day of channel statistics (ES-backed)."""

    date: str
    message_count: int
    reaction_count: int
    hourly_message_counts: Tuple[int, ...]


@dataclass(frozen=True)
class WeeklyStats:
    """Aggregated week window plus daily rows and top posts."""

    start_date: str
    end_date: str
    message_count: int
    reaction_count: int
    top_posts: Tuple[dict[str, Any], ...]
    hourly_message_counts: Tuple[int, ...]
    error_dates: Tuple[str, ...]
    daily_stats: Tuple[DailyStats, ...]

    @classmethod
    def empty(cls) -> "WeeklyStats":
        return cls(
            start_date="",
            end_date="",
            message_count=0,
            reaction_count=0,
            top_posts=(),
            hourly_message_counts=(),
            error_dates=(),
            daily_stats=(),
        )
