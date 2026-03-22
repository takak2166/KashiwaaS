"""
Date Utility Module
Provides functions for date and time conversion and manipulation
"""

import datetime
import os
from typing import Optional, Tuple, Union

import pytz

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Timezone: use TIMEZONE env if set (same as AppConfig), avoid importing config at module load
DEFAULT_TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tokyo"))


def get_current_time(timezone: Optional[pytz.timezone] = None) -> datetime.datetime:
    """
    Get the current time

    Args:
        timezone: Timezone (default timezone if not specified)

    Returns:
        datetime.datetime: Current time with timezone
    """
    tz = timezone or DEFAULT_TIMEZONE
    return datetime.datetime.now(tz)


def convert_to_timestamp(dt: Union[datetime.datetime, str]) -> float:
    """
    Convert datetime to Unix timestamp (seconds)

    Args:
        dt: Datetime object or ISO format datetime string

    Returns:
        float: Unix timestamp (seconds)
    """
    if isinstance(dt, str):
        dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DEFAULT_TIMEZONE)

    return dt.timestamp()


def convert_from_timestamp(timestamp: float, timezone: Optional[pytz.timezone] = None) -> datetime.datetime:
    """
    Convert Unix timestamp (seconds) to datetime object

    Args:
        timestamp: Unix timestamp (seconds)
        timezone: Timezone (default timezone if not specified)

    Returns:
        datetime.datetime: Datetime object with timezone
    """
    tz = timezone or DEFAULT_TIMEZONE
    return datetime.datetime.fromtimestamp(timestamp, tz)


def date_range_as_timestamps(days: int, end: datetime.datetime) -> Tuple[float, float]:
    """
    Inclusive calendar range [end - days, end] as Unix timestamps (start-of-day to end-of-day).

    Caller supplies ``end`` (e.g. from CLI or ``get_current_time()`` in the shell).
    """
    start = end - datetime.timedelta(days=days)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    return convert_to_timestamp(start), convert_to_timestamp(end_day)


def is_weekend(dt: datetime.datetime) -> bool:
    """
    Determine if the specified date is a weekend (Saturday or Sunday)

    Args:
        dt: Datetime object

    Returns:
        bool: True if weekend
    """
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday


def get_day_of_week(dt: datetime.datetime) -> int:
    """
    Get day of week as a number (0=Monday, 6=Sunday)

    Args:
        dt: Datetime object

    Returns:
        int: Day of week (0-6)
    """
    return dt.weekday()


def get_hour_of_day(dt: datetime.datetime) -> int:
    """
    Get hour of day (0-23)

    Args:
        dt: Datetime object

    Returns:
        int: Hour of day (0-23)
    """
    return dt.hour
