"""
設定管理モジュール
環境変数からの設定読み込みと検証を行います
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger(__name__)

# .envファイルの読み込み
dotenv_path = Path(".env")
if dotenv_path.exists():
    logger.info(f"Loading environment from {dotenv_path.absolute()}")
    load_dotenv(dotenv_path)
else:
    logger.warning(f".env file not found at {dotenv_path.absolute()}")


@dataclass
class SlackConfig:
    """Slack API設定"""
    api_token: str
    channel_id: str


@dataclass
class ElasticsearchConfig:
    """Elasticsearch設定"""
    host: str
    user: Optional[str] = None
    password: Optional[str] = None


@dataclass
class AppConfig:
    """アプリケーション全体の設定"""
    slack: SlackConfig
    elasticsearch: ElasticsearchConfig
    timezone: str


def load_config() -> AppConfig:
    """
    環境変数から設定を読み込み、AppConfig オブジェクトを返します

    Returns:
        AppConfig: アプリケーション設定
    
    Raises:
        ValueError: 必須の環境変数が設定されていない場合
    """
    # Slack設定の読み込み
    slack_token = os.getenv("SLACK_API_TOKEN")
    slack_channel = os.getenv("SLACK_CHANNEL_ID")
    
    if not slack_token:
        raise ValueError("SLACK_API_TOKEN environment variable is required")
    if not slack_channel:
        raise ValueError("SLACK_CHANNEL_ID environment variable is required")
    
    # Elasticsearch設定の読み込み
    es_host = os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")
    es_user = os.getenv("ELASTICSEARCH_USER")
    es_password = os.getenv("ELASTICSEARCH_PASSWORD")
    
    # タイムゾーン設定
    timezone = os.getenv("TIMEZONE", "Asia/Tokyo")
    
    return AppConfig(
        slack=SlackConfig(
            api_token=slack_token,
            channel_id=slack_channel,
        ),
        elasticsearch=ElasticsearchConfig(
            host=es_host,
            user=es_user,
            password=es_password,
        ),
        timezone=timezone,
    )


# グローバル設定オブジェクト
try:
    config = load_config()
    logger.info(f"Configuration loaded successfully. Timezone: {config.timezone}")
except ValueError as e:
    logger.error(f"Failed to load configuration: {e}")
    config = None