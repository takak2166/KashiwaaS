"""
日付操作ユーティリティ
日付と時刻の変換、操作を行う関数を提供します
"""
import datetime
from typing import Optional, Tuple, Union

import pytz

from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# タイムゾーン設定
DEFAULT_TIMEZONE = pytz.timezone(config.timezone if config else "Asia/Tokyo")


def get_current_time(timezone: Optional[pytz.timezone] = None) -> datetime.datetime:
    """
    現在時刻を取得します

    Args:
        timezone: タイムゾーン（指定がない場合はデフォルトタイムゾーン）

    Returns:
        datetime.datetime: 現在時刻（タイムゾーン付き）
    """
    tz = timezone or DEFAULT_TIMEZONE
    return datetime.datetime.now(tz)


def convert_to_timestamp(dt: Union[datetime.datetime, str]) -> float:
    """
    日時をUnixタイムスタンプ（秒）に変換します

    Args:
        dt: 日時オブジェクトまたはISO形式の日時文字列

    Returns:
        float: Unixタイムスタンプ（秒）
    """
    if isinstance(dt, str):
        dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DEFAULT_TIMEZONE)
    
    return dt.timestamp()


def convert_from_timestamp(timestamp: float, timezone: Optional[pytz.timezone] = None) -> datetime.datetime:
    """
    Unixタイムスタンプ（秒）を日時オブジェクトに変換します

    Args:
        timestamp: Unixタイムスタンプ（秒）
        timezone: タイムゾーン（指定がない場合はデフォルトタイムゾーン）

    Returns:
        datetime.datetime: 日時オブジェクト（タイムゾーン付き）
    """
    tz = timezone or DEFAULT_TIMEZONE
    return datetime.datetime.fromtimestamp(timestamp, tz)


def get_date_range(days: int, end_date: Optional[datetime.datetime] = None) -> Tuple[float, float]:
    """
    指定日数分の日付範囲をタイムスタンプで取得します

    Args:
        days: 日数
        end_date: 終了日（指定がない場合は現在日時）

    Returns:
        Tuple[float, float]: (開始タイムスタンプ, 終了タイムスタンプ)
    """
    end = end_date or get_current_time()
    start = end - datetime.timedelta(days=days)
    
    # 日付の始まりと終わりに調整
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return convert_to_timestamp(start), convert_to_timestamp(end)


def is_weekend(dt: Optional[datetime.datetime] = None) -> bool:
    """
    指定日が週末（土日）かどうかを判定します

    Args:
        dt: 日時オブジェクト（指定がない場合は現在日時）

    Returns:
        bool: 週末の場合はTrue
    """
    dt = dt or get_current_time()
    return dt.weekday() >= 5  # 5=土曜日, 6=日曜日


def get_day_of_week(dt: Optional[datetime.datetime] = None) -> int:
    """
    曜日を数値で取得します（0=月曜日, 6=日曜日）

    Args:
        dt: 日時オブジェクト（指定がない場合は現在日時）

    Returns:
        int: 曜日（0-6）
    """
    dt = dt or get_current_time()
    return dt.weekday()


def get_hour_of_day(dt: Optional[datetime.datetime] = None) -> int:
    """
    時間（0-23）を取得します

    Args:
        dt: 日時オブジェクト（指定がない場合は現在日時）

    Returns:
        int: 時間（0-23）
    """
    dt = dt or get_current_time()
    return dt.hour