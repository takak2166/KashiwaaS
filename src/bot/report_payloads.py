"""
Pure construction of report text and upload plans (no Slack/ES I/O).
"""

from dataclasses import dataclass
from typing import List, Optional

from src.analysis.types import DailyStats, WeeklyStats
from src.bot.formatter import (
    format_chart_title,
    format_daily_report,
    format_dashboard_title,
    format_weekly_report,
)


@dataclass(frozen=True)
class FileUploadItem:
    """One file to upload with Slack title."""

    path: str
    title: str


@dataclass(frozen=True)
class DailyReportPayload:
    """Formatted daily report ready to log or post."""

    formatted_text: str
    stats: DailyStats


@dataclass(frozen=True)
class WeeklyReportPayload:
    """Formatted weekly report plus ordered file uploads."""

    formatted_text: str
    stats: WeeklyStats
    upload_plan: List[FileUploadItem]


def build_daily_report_payload(stats: DailyStats) -> DailyReportPayload:
    """Build display text from daily stats."""
    return DailyReportPayload(formatted_text=format_daily_report(stats), stats=stats)


def build_weekly_upload_plan(
    stats: WeeklyStats,
    chart_paths: dict[str, Optional[str]],
    kibana_screenshot: Optional[str],
) -> List[FileUploadItem]:
    """Ordered list of chart/dashboard files to upload after the main message."""
    period = f"{stats.start_date} to {stats.end_date}"
    items: List[FileUploadItem] = []
    for chart_type, path in chart_paths.items():
        if path:
            items.append(
                FileUploadItem(
                    path=path,
                    title=format_chart_title(chart_type, period, is_weekly=True),
                )
            )
    if kibana_screenshot:
        items.append(
            FileUploadItem(
                path=kibana_screenshot,
                title=format_dashboard_title(period, is_weekly=True),
            )
        )
    return items


def build_weekly_report_payload(
    stats: WeeklyStats,
    chart_paths: dict[str, Optional[str]],
    kibana_screenshot: Optional[str],
) -> WeeklyReportPayload:
    """Build formatted weekly text and upload plan from stats and artifact paths."""
    text = format_weekly_report(stats)
    plan = build_weekly_upload_plan(stats, chart_paths, kibana_screenshot)
    return WeeklyReportPayload(formatted_text=text, stats=stats, upload_plan=plan)
