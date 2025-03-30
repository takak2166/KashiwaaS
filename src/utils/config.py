"""
Configuration Management Module
Loads and validates settings from environment variables
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Load .env file
dotenv_path = Path(".env")
if dotenv_path.exists():
    logger.info(f"Loading environment from {dotenv_path.absolute()}")
    load_dotenv(dotenv_path)
else:
    logger.warning(f".env file not found at {dotenv_path.absolute()}")


@dataclass
class SlackConfig:
    """Slack API configuration"""
    api_token: str
    channel_id: str
    alert_channel_id: Optional[str] = None


@dataclass
class AlertConfig:
    """Alert configuration"""
    min_level: str = "WARNING"  # INFO, WARNING, ERROR, CRITICAL
    throttle_seconds: int = 300
    max_per_hour: int = 10


@dataclass
class ElasticsearchConfig:
    """Elasticsearch configuration"""
    host: str
    user: Optional[str] = None
    password: Optional[str] = None


@dataclass
class AppConfig:
    """Application-wide configuration"""
    slack: SlackConfig
    elasticsearch: ElasticsearchConfig
    timezone: str
    alert: AlertConfig


def load_config() -> AppConfig:
    """
    Load settings from environment variables and return an AppConfig object

    Returns:
        AppConfig: Application configuration
    
    Raises:
        ValueError: If required environment variables are not set
    """
    # Load Slack configuration
    slack_token = os.getenv("SLACK_API_TOKEN")
    slack_channel = os.getenv("SLACK_CHANNEL_ID")
    slack_alert_channel = os.getenv("SLACK_ALERT_CHANNEL_ID")
    
    if not slack_token:
        raise ValueError("SLACK_API_TOKEN environment variable is required")
    if not slack_channel:
        raise ValueError("SLACK_CHANNEL_ID environment variable is required")
    
    # Load Elasticsearch configuration
    es_host = os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")
    es_user = os.getenv("ELASTICSEARCH_USER")
    es_password = os.getenv("ELASTICSEARCH_PASSWORD")
    
    # Load Alert configuration
    alert_min_level = os.getenv("ALERT_MIN_LEVEL", "WARNING")
    alert_throttle_seconds = int(os.getenv("ALERT_THROTTLE_SECONDS", "300"))
    alert_max_per_hour = int(os.getenv("ALERT_MAX_PER_HOUR", "10"))
    
    # Timezone configuration
    timezone = os.getenv("TIMEZONE", "Asia/Tokyo")
    
    return AppConfig(
        slack=SlackConfig(
            api_token=slack_token,
            channel_id=slack_channel,
            alert_channel_id=slack_alert_channel,
        ),
        elasticsearch=ElasticsearchConfig(
            host=es_host,
            user=es_user,
            password=es_password,
        ),
        timezone=timezone,
        alert=AlertConfig(
            min_level=alert_min_level,
            throttle_seconds=alert_throttle_seconds,
            max_per_hour=alert_max_per_hour,
        ),
    )


# Global configuration object
try:
    config = load_config()
    logger.info(f"Configuration loaded successfully. Timezone: {config.timezone}")
except ValueError as e:
    logger.error(f"Failed to load configuration: {e}")
    config = None