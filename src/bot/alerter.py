"""
Alerter: Slack alerts with explicit AppConfig (no global config import).
"""

from __future__ import annotations

import time
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from src.slack.client import SlackClient
from src.utils.config import AppConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""

    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


_LEVEL_MAP = {
    "INFO": AlertLevel.INFO,
    "WARNING": AlertLevel.WARNING,
    "ERROR": AlertLevel.ERROR,
    "CRITICAL": AlertLevel.CRITICAL,
}


class Alerter:
    """
    Alerter: throttling, formatting, optional Slack delivery via injected SlackClient.
    """

    _last_alerts: Dict[str, float] = {}
    _alert_counts: Dict[str, int] = {}
    _sent_alerts: Set[str] = set()

    def __init__(
        self,
        *,
        slack_client: Optional[SlackClient] = None,
        alert_channel_id: Optional[str] = None,
        min_level: AlertLevel = AlertLevel.WARNING,
        throttle_seconds: int = 300,
        max_alerts_per_hour: int = 10,
    ):
        self.alert_channel_id = alert_channel_id
        if not self.alert_channel_id:
            logger.warning("Alert channel ID not specified, alerts will be logged but not sent to Slack")

        self.min_level = min_level
        self.throttle_seconds = throttle_seconds
        self.max_alerts_per_hour = max_alerts_per_hour
        self.hourly_alert_count = 0
        self.hour_start_time = time.time()

        self.slack_client = slack_client

        logger.info(
            f"Alerter initialized with min_level={min_level.name}, "
            f"throttle_seconds={throttle_seconds}, "
            f"max_alerts_per_hour={max_alerts_per_hour}"
        )

    def alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        alert_key: Optional[str] = None,
        notify_users: Optional[List[str]] = None,
    ) -> bool:
        if level.value < self.min_level.value:
            logger.debug(f"Alert level {level.name} below minimum {self.min_level.name}, not sending")
            return False

        if not alert_key:
            alert_key = f"{level.name}:{message}"

        current_time = time.time()

        if current_time - self.hour_start_time > 3600:
            self.hourly_alert_count = 0
            self.hour_start_time = current_time

        if self.hourly_alert_count >= self.max_alerts_per_hour:
            logger.warning(f"Hourly alert limit reached ({self.max_alerts_per_hour}), not sending alert: {message}")
            return False

        last_time = self._last_alerts.get(alert_key, 0)
        if current_time - last_time < self.throttle_seconds:
            self._alert_counts[alert_key] = self._alert_counts.get(alert_key, 0) + 1
            logger.debug(f"Throttling alert {alert_key}, occurred {self._alert_counts[alert_key]} times")
            return False

        formatted_message = self._format_alert(
            message=message,
            level=level,
            title=title,
            details=details,
            alert_key=alert_key,
            notify_users=notify_users,
            count=self._alert_counts.get(alert_key, 0),
        )

        log_method = getattr(logger, level.name.lower(), logger.warning)
        log_method(f"ALERT: {message}")

        sent = False
        if self.slack_client:
            try:
                self.slack_client.post_message(
                    text=formatted_message,
                    blocks=self._create_alert_blocks(
                        message=message,
                        formatted_message=formatted_message,
                        level=level,
                        title=title,
                        details=details,
                        alert_key=alert_key,
                        count=self._alert_counts.get(alert_key, 0),
                    ),
                )
                sent = True
                self.hourly_alert_count += 1

                if alert_key in self._alert_counts:
                    self._alert_counts[alert_key] = 0

                self._sent_alerts.add(alert_key)

            except Exception as e:
                logger.error(f"Failed to send alert to Slack: {e}")

        self._last_alerts[alert_key] = current_time

        return sent

    def _format_alert(
        self,
        message: str,
        level: AlertLevel,
        title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        alert_key: Optional[str] = None,
        notify_users: Optional[List[str]] = None,
        count: int = 0,
    ) -> str:
        level_emoji = {
            AlertLevel.INFO: ":information_source:",
            AlertLevel.WARNING: ":warning:",
            AlertLevel.ERROR: ":x:",
            AlertLevel.CRITICAL: ":rotating_light:",
        }.get(level, ":warning:")

        if not title:
            title = f"{level.name} Alert"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        mentions = ""
        if notify_users:
            mentions = " " + " ".join([f"<@{user_id}>" for user_id in notify_users])

        if level == AlertLevel.CRITICAL:
            mentions += " <!channel>"

        count_str = f" (occurred {count + 1} times)" if count > 0 else ""

        formatted_message = f"{level_emoji} *{title}*{mentions}{count_str}\n"
        formatted_message += f"*Time:* {timestamp}\n"
        formatted_message += f"*Message:* {message}\n"

        if details:
            formatted_message += "*Details:*\n"
            for key, value in details.items():
                formatted_message += f"• {key}: {value}\n"

        return formatted_message

    def _create_alert_blocks(
        self,
        message: str,
        formatted_message: str,
        level: AlertLevel,
        title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        alert_key: Optional[str] = None,
        count: int = 0,
    ) -> List[Dict[str, Any]]:
        if not title:
            title = f"{level.name} Alert"

        if count > 0:
            title = f"{title} (occurred {count + 1} times)"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title, "emoji": True},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": formatted_message}},
        ]

        blocks.append({"type": "divider"})

        return blocks


_alerter: Optional[Alerter] = None


def init_alerter(cfg: AppConfig) -> None:
    """Build the process-wide Alerter from ``AppConfig`` (call from entrypoints)."""
    global _alerter

    slack_for_alerts: Optional[SlackClient] = None
    if cfg.slack.alert_channel_id and cfg.slack.api_token:
        slack_for_alerts = SlackClient(
            token=cfg.slack.api_token,
            channel_id=cfg.slack.alert_channel_id,
            dummy=False,
        )

    min_lvl = _LEVEL_MAP.get(cfg.alert.min_level.upper(), AlertLevel.WARNING)

    _alerter = Alerter(
        slack_client=slack_for_alerts,
        alert_channel_id=cfg.slack.alert_channel_id,
        min_level=min_lvl,
        throttle_seconds=cfg.alert.throttle_seconds,
        max_alerts_per_hour=cfg.alert.max_per_hour,
    )


def get_alerter() -> Alerter:
    if _alerter is None:
        raise RuntimeError("init_alerter(load_config()) must be called before using alerts")
    return _alerter


def alert(
    message: str,
    level: AlertLevel = AlertLevel.WARNING,
    title: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    alert_key: Optional[str] = None,
    notify_users: Optional[List[str]] = None,
) -> bool:
    return get_alerter().alert(
        message=message,
        level=level,
        title=title,
        details=details,
        alert_key=alert_key,
        notify_users=notify_users,
    )
