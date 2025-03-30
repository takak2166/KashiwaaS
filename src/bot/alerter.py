"""
Alerter Module
Provides functionality for sending alerts to Slack
"""
import time
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Set

from src.slack.client import SlackClient
from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class Alerter:
    """
    Alerter class for sending alerts to Slack
    
    Handles alert throttling, formatting, and delivery to Slack.
    """
    
    # Class variables for alert throttling
    _last_alerts: Dict[str, float] = {}  # key -> timestamp
    _alert_counts: Dict[str, int] = {}   # key -> count
    _sent_alerts: Set[str] = set()       # Set of alert keys that have been sent
    
    def __init__(
        self,
        alert_channel_id: Optional[str] = None,
        min_level: AlertLevel = AlertLevel.WARNING,
        throttle_seconds: int = 300,  # 5 minutes
        max_alerts_per_hour: int = 10
    ):
        """
        Initialize the Alerter
        
        Args:
            alert_channel_id: Slack channel ID for alerts (if not specified, retrieved from environment variables)
            min_level: Minimum alert level to send
            throttle_seconds: Minimum seconds between identical alerts
            max_alerts_per_hour: Maximum number of alerts per hour
        """
        self.alert_channel_id = alert_channel_id or (config.slack.alert_channel_id if config else None)
        if not self.alert_channel_id:
            logger.warning("Alert channel ID not specified, alerts will be logged but not sent to Slack")
        
        self.min_level = min_level
        self.throttle_seconds = throttle_seconds
        self.max_alerts_per_hour = max_alerts_per_hour
        self.hourly_alert_count = 0
        self.hour_start_time = time.time()
        
        # Initialize Slack client if channel ID is provided
        self.slack_client = SlackClient(channel_id=self.alert_channel_id) if self.alert_channel_id else None
        
        logger.info(f"Alerter initialized with min_level={min_level.name}, "
                   f"throttle_seconds={throttle_seconds}, "
                   f"max_alerts_per_hour={max_alerts_per_hour}")
    
    def alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        alert_key: Optional[str] = None,
        notify_users: Optional[List[str]] = None
    ) -> bool:
        """
        Send an alert
        
        Args:
            message: Alert message
            level: Alert level
            title: Alert title (optional)
            details: Additional details (optional)
            alert_key: Key for throttling identical alerts (optional)
            notify_users: List of user IDs to notify (optional)
            
        Returns:
            bool: True if alert was sent, False otherwise
        """
        # Check if alert level meets minimum threshold
        if level.value < self.min_level.value:
            logger.debug(f"Alert level {level.name} below minimum {self.min_level.name}, not sending")
            return False
        
        # Generate alert key if not provided
        if not alert_key:
            alert_key = f"{level.name}:{message}"
        
        # Check for throttling
        current_time = time.time()
        
        # Reset hourly counter if an hour has passed
        if current_time - self.hour_start_time > 3600:
            self.hourly_alert_count = 0
            self.hour_start_time = current_time
        
        # Check if we've exceeded the hourly limit
        if self.hourly_alert_count >= self.max_alerts_per_hour:
            logger.warning(f"Hourly alert limit reached ({self.max_alerts_per_hour}), not sending alert: {message}")
            return False
        
        # Check if this alert was sent recently
        last_time = self._last_alerts.get(alert_key, 0)
        if current_time - last_time < self.throttle_seconds:
            # Update count for this alert
            self._alert_counts[alert_key] = self._alert_counts.get(alert_key, 0) + 1
            logger.debug(f"Throttling alert {alert_key}, occurred {self._alert_counts[alert_key]} times")
            return False
        
        # Format the alert message
        formatted_message = self._format_alert(
            message=message,
            level=level,
            title=title,
            details=details,
            alert_key=alert_key,
            notify_users=notify_users,
            count=self._alert_counts.get(alert_key, 0)
        )
        
        # Log the alert
        log_method = getattr(logger, level.name.lower(), logger.warning)
        log_method(f"ALERT: {message}")
        
        # Send to Slack if client is available
        sent = False
        if self.slack_client:
            try:
                # Use formatted_message as fallback text for clients that don't support blocks
                self.slack_client.post_message(
                    text=formatted_message,
                    blocks=self._create_alert_blocks(
                        message=message,
                        formatted_message=formatted_message,
                        level=level,
                        title=title,
                        details=details,
                        alert_key=alert_key,
                        count=self._alert_counts.get(alert_key, 0)
                    )
                )
                sent = True
                self.hourly_alert_count += 1
                
                # Reset the count for this alert
                if alert_key in self._alert_counts:
                    self._alert_counts[alert_key] = 0
                
                # Add to sent alerts set
                self._sent_alerts.add(alert_key)
                
            except Exception as e:
                logger.error(f"Failed to send alert to Slack: {e}")
        
        # Update last alert time
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
        count: int = 0
    ) -> str:
        """
        Format alert message
        
        Args:
            message: Alert message
            level: Alert level
            title: Alert title (optional)
            details: Additional details (optional)
            alert_key: Alert key (optional)
            notify_users: List of user IDs to notify (optional)
            count: Number of times this alert has occurred (optional)
            
        Returns:
            str: Formatted alert message
        """
        # Level emoji
        level_emoji = {
            AlertLevel.INFO: ":information_source:",
            AlertLevel.WARNING: ":warning:",
            AlertLevel.ERROR: ":x:",
            AlertLevel.CRITICAL: ":rotating_light:",
        }.get(level, ":warning:")
        
        # Format title
        if not title:
            title = f"{level.name} Alert"
        
        # Format timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format user mentions
        mentions = ""
        if notify_users:
            mentions = " " + " ".join([f"<@{user_id}>" for user_id in notify_users])
        
        # Add @channel mention for CRITICAL alerts
        if level == AlertLevel.CRITICAL:
            mentions += " <!channel>"
        
        # Format count
        count_str = f" (occurred {count+1} times)" if count > 0 else ""
        
        # Format message
        formatted_message = f"{level_emoji} *{title}*{mentions}{count_str}\n"
        formatted_message += f"*Time:* {timestamp}\n"
        formatted_message += f"*Message:* {message}\n"
        
        # Add details if provided
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
        count: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Create Slack blocks for alert
        
        Args:
            message: Alert message
            level: Alert level
            title: Alert title (optional)
            details: Additional details (optional)
            alert_key: Alert key (optional)
            count: Number of times this alert has occurred (optional)
            
        Returns:
            List[Dict[str, Any]]: Slack blocks
        """
        # Level color
        level_color = {
            AlertLevel.INFO: "#2196F3",      # Blue
            AlertLevel.WARNING: "#FFC107",   # Amber
            AlertLevel.ERROR: "#F44336",     # Red
            AlertLevel.CRITICAL: "#9C27B0",  # Purple
        }.get(level, "#FFC107")
        
        # Format title
        if not title:
            title = f"{level.name} Alert"
        
        # Format count
        if count > 0:
            title = f"{title} (occurred {count+1} times)"
        
        # Create blocks - simplified to avoid duplication with formatted_message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": formatted_message
                }
            }
        ]
        
        # Add divider
        blocks.append({"type": "divider"})
        
        return blocks


# Global alerter instance
_alerter: Optional[Alerter] = None


def get_alerter() -> Alerter:
    """
    Get the global alerter instance
    
    Returns:
        Alerter: Global alerter instance
    """
    global _alerter
    if _alerter is None:
        _alerter = Alerter()
    return _alerter


def alert(
    message: str,
    level: AlertLevel = AlertLevel.WARNING,
    title: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    alert_key: Optional[str] = None,
    notify_users: Optional[List[str]] = None
) -> bool:
    """
    Send an alert using the global alerter
    
    Args:
        message: Alert message
        level: Alert level
        title: Alert title (optional)
        details: Additional details (optional)
        alert_key: Key for throttling identical alerts (optional)
        notify_users: List of user IDs to notify (optional)
        
    Returns:
        bool: True if alert was sent, False otherwise
    """
    return get_alerter().alert(
        message=message,
        level=level,
        title=title,
        details=details,
        alert_key=alert_key,
        notify_users=notify_users
    )