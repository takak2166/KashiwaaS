"""
Date Utility Module
Provides functions for date and time conversion and manipulation
"""

import datetime
from typing import Optional, Tuple, Union

import pytz

from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Timezone configuration
DEFAULT_TIMEZONE = pytz.timezone(config.timezone if config else "Asia/Tokyo")


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


def get_date_range(days: int, end_date: Optional[datetime.datetime] = None) -> Tuple[float, float]:
    """
    Get date range as timestamps for the specified number of days

    Args:
        days: Number of days
        end_date: End date (current time if not specified)

    Returns:
        Tuple[float, float]: (start timestamp, end timestamp)
    """
    end = end_date or get_current_time()
    start = end - datetime.timedelta(days=days)

    # Adjust to start and end of day
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    return convert_to_timestamp(start), convert_to_timestamp(end)


def is_weekend(dt: Optional[datetime.datetime] = None) -> bool:
    """
    Determine if the specified date is a weekend (Saturday or Sunday)

    Args:
        dt: Datetime object (current time if not specified)

    Returns:
        bool: True if weekend
    """
    dt = dt or get_current_time()
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday


def get_day_of_week(dt: Optional[datetime.datetime] = None) -> int:
    """
    Get day of week as a number (0=Monday, 6=Sunday)

    Args:
        dt: Datetime object (current time if not specified)

    Returns:
        int: Day of week (0-6)
    """
    dt = dt or get_current_time()
    return dt.weekday()


def get_hour_of_day(dt: Optional[datetime.datetime] = None) -> int:
    """
    Get hour of day (0-23)

    Args:
        dt: Datetime object (current time if not specified)

    Returns:
        int: Hour of day (0-23)
    """
    dt = dt or get_current_time()
    return dt.hour
