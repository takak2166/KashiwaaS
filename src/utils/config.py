"""
Configuration: parse environment into immutable AppConfig (no import-time globals).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default for CURSOR_POLL_TIMEOUT / CursorClient.poll_timeout (seconds).
DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS = 600

# Slack thread -> Cursor agent mapping keys in Valkey (30 days, sliding TTL).
DEFAULT_VALKEY_THREAD_TTL_SECONDS = 30 * 24 * 3600
# Upper bound for VALKEY_THREAD_TTL_SECONDS (catch typos; Redis TTL is effectively capped in practice).
MAX_VALKEY_THREAD_TTL_SECONDS = 10 * 365 * 24 * 3600


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class SlackConfig:
    """Slack API configuration (ingestion / reports)."""

    api_token: Optional[str]
    channel_id: Optional[str]
    channel_name: Optional[str]
    alert_channel_id: Optional[str] = None


@dataclass(frozen=True)
class AlertConfig:
    """Alert configuration."""

    min_level: str = "WARNING"
    throttle_seconds: int = 300
    max_per_hour: int = 10


@dataclass(frozen=True)
class ElasticsearchConfig:
    """Elasticsearch configuration."""

    host: str
    user: Optional[str] = None
    password: Optional[str] = None


@dataclass(frozen=True)
class KibanaConfig:
    """Kibana configuration."""

    host: str
    username: Optional[str] = None
    password: Optional[str] = None
    weekly_dashboard_id: Optional[str] = None


@dataclass(frozen=True)
class CursorConfig:
    """Cursor Cloud Agents API configuration."""

    api_key: Optional[str] = None
    source_repository: str = "https://github.com/takak2166/KashiwaaS"
    source_ref: str = "main"
    poll_interval: int = 5
    poll_timeout: int = DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS
    model: Optional[str] = "composer-2"
    conversation_retry_max_retries: int = 4
    conversation_retry_delay_seconds: float = 1.5
    conversation_text_stabilize_interval_seconds: float = 1.0
    conversation_text_stabilize_required_matches: int = 3
    conversation_text_stabilize_max_rounds: int = 60


@dataclass(frozen=True)
class BotConfig:
    """Bot (Socket Mode) configuration."""

    app_token: Optional[str] = None
    bot_token: Optional[str] = None


@dataclass(frozen=True)
class MattermostConfig:
    """Mattermost bot (WebSocket + PAT). Optional in ``AppConfig``; required when running the MM entrypoint."""

    url: str
    pat: str
    # May be empty at load time; Mattermost bot resolves from PAT (users/me) after login.
    bot_user_id: str
    driver_scheme: str
    driver_host: str
    driver_port: int
    verify_tls: bool = True
    log_raw_websocket: bool = False
    # Extra @name tokens for open-channel mentions (env MATTERMOST_BOT_USERNAME, comma-separated).
    bot_mention_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValkeyConfig:
    """Valkey (Redis protocol) for persistent Slack thread to Cursor agent mapping."""

    url: str
    thread_ttl_seconds: int = DEFAULT_VALKEY_THREAD_TTL_SECONDS


@dataclass(frozen=True)
class AppConfig:
    """Application-wide configuration."""

    slack: SlackConfig
    elasticsearch: ElasticsearchConfig
    kibana: KibanaConfig
    selenium_host: str
    timezone: str
    alert: AlertConfig
    cursor: CursorConfig
    bot: BotConfig
    valkey: ValkeyConfig
    mattermost: Optional[MattermostConfig] = None


def apply_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """Load ``.env`` from the project root once (call from CLI / bot ``main``)."""
    path = dotenv_path if dotenv_path is not None else Path(".env")
    if path.exists():
        logger.info(f"Loading environment from {path.absolute()}")
        load_dotenv(path)
    else:
        logger.warning(f".env file not found at {path.absolute()}")


def _get_str(env: Mapping[str, str], key: str, default: Optional[str] = None) -> Optional[str]:
    v = env.get(key)
    if v is None or v == "":
        return default
    return v


def _get_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{key} must be a valid integer (got {raw!r})") from e


def _get_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise ConfigError(f"{key} must be a valid float (got {raw!r})") from e


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """
    Build AppConfig from environment variables.

    Does not read ``.env``; call :func:`apply_dotenv` first if needed.

    Args:
        env: Mapping to read (default: ``os.environ``).

    Returns:
        Parsed configuration.
    """
    e = env if env is not None else os.environ

    es_host = _get_str(e, "ELASTICSEARCH_HOST", "http://localhost:9200") or "http://localhost:9200"

    selenium = _get_str(e, "SELENIUM_HOST") or _get_str(e, "SELENIIUM_HOST") or "http://localhost:4444/wd/hub"
    kibana_host = _get_str(e, "KIBANA_HOST", "http://localhost:5601")

    conv_max = _get_int(e, "CURSOR_CONVERSATION_RETRY_MAX_RETRIES", 4)
    conv_delay = _get_float(e, "CURSOR_CONVERSATION_RETRY_DELAY_SECONDS", 1.5)
    conv_stab_interval = _get_float(e, "CURSOR_CONVERSATION_TEXT_STABILIZE_INTERVAL_SECONDS", 1.0)
    conv_stab_matches = _get_int(e, "CURSOR_CONVERSATION_TEXT_STABILIZE_REQUIRED_MATCHES", 3)
    conv_stab_max = _get_int(e, "CURSOR_CONVERSATION_TEXT_STABILIZE_MAX_ROUNDS", 60)
    if conv_stab_interval < 0:
        raise ConfigError("CURSOR_CONVERSATION_TEXT_STABILIZE_INTERVAL_SECONDS must be >= 0")
    if conv_stab_matches < 1:
        raise ConfigError("CURSOR_CONVERSATION_TEXT_STABILIZE_REQUIRED_MATCHES must be >= 1")
    if conv_stab_max < 1:
        raise ConfigError("CURSOR_CONVERSATION_TEXT_STABILIZE_MAX_ROUNDS must be >= 1")

    valkey_url = _get_str(e, "VALKEY_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
    valkey_ttl = _get_int(e, "VALKEY_THREAD_TTL_SECONDS", DEFAULT_VALKEY_THREAD_TTL_SECONDS)
    if valkey_ttl < 0:
        raise ConfigError("VALKEY_THREAD_TTL_SECONDS must be >= 0")
    if valkey_ttl > MAX_VALKEY_THREAD_TTL_SECONDS:
        raise ConfigError(
            f"VALKEY_THREAD_TTL_SECONDS must be <= {MAX_VALKEY_THREAD_TTL_SECONDS} (~10 years); got {valkey_ttl}"
        )

    mm_url_raw = _get_str(e, "MATTERMOST_URL")
    mm_pat = _get_str(e, "MATTERMOST_PAT")
    mm_bot_uid = _get_str(e, "MATTERMOST_BOT_USER_ID")
    mattermost: Optional[MattermostConfig] = None
    if mm_url_raw or mm_pat or mm_bot_uid:
        if not mm_url_raw or not mm_pat:
            raise ConfigError(
                "Mattermost is partially configured: set MATTERMOST_URL and MATTERMOST_PAT together "
                "(optional MATTERMOST_BOT_USER_ID; omit all Mattermost vars for Slack-only)"
            )
        parsed = urlparse(mm_url_raw if "://" in mm_url_raw else f"https://{mm_url_raw}")
        if not parsed.hostname:
            raise ConfigError("MATTERMOST_URL must include a hostname (e.g. https://chat.example.com)")
        scheme = (parsed.scheme or "https").lower()
        if scheme not in ("http", "https"):
            raise ConfigError(f"MATTERMOST_URL scheme must be http or https (got {parsed.scheme!r})")
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 8065
        mm_verify_raw = (_get_str(e, "MATTERMOST_VERIFY_TLS", "true") or "true").lower()
        verify_tls = mm_verify_raw not in ("0", "false", "no", "off")
        log_raw = (_get_str(e, "MATTERMOST_LOG_RAW_WEBSOCKET", "false") or "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        mm_names_raw = _get_str(e, "MATTERMOST_BOT_USERNAME", "") or ""
        bot_mention_names = tuple(
            p.strip() for p in mm_names_raw.split(",") if p.strip()
        )
        mattermost = MattermostConfig(
            url=mm_url_raw,
            pat=mm_pat,
            bot_user_id=(mm_bot_uid or "").strip(),
            driver_scheme=scheme,
            driver_host=parsed.hostname,
            driver_port=port,
            verify_tls=verify_tls,
            log_raw_websocket=log_raw,
            bot_mention_names=bot_mention_names,
        )

    return AppConfig(
        slack=SlackConfig(
            api_token=_get_str(e, "SLACK_API_TOKEN"),
            channel_id=_get_str(e, "SLACK_CHANNEL_ID"),
            channel_name=_get_str(e, "SLACK_CHANNEL_NAME"),
            alert_channel_id=_get_str(e, "SLACK_ALERT_CHANNEL_ID"),
        ),
        elasticsearch=ElasticsearchConfig(
            host=es_host,
            user=_get_str(e, "ELASTICSEARCH_USER"),
            password=_get_str(e, "ELASTICSEARCH_PASSWORD"),
        ),
        kibana=KibanaConfig(
            host=kibana_host,
            username=_get_str(e, "KIBANA_USERNAME"),
            password=_get_str(e, "KIBANA_PASSWORD"),
            weekly_dashboard_id=_get_str(e, "KIBANA_WEEKLY_DASHBOARD_ID"),
        ),
        selenium_host=selenium,
        timezone=_get_str(e, "TIMEZONE", "Asia/Tokyo") or "Asia/Tokyo",
        alert=AlertConfig(
            min_level=_get_str(e, "ALERT_MIN_LEVEL", "WARNING") or "WARNING",
            throttle_seconds=_get_int(e, "ALERT_THROTTLE_SECONDS", 300),
            max_per_hour=_get_int(e, "ALERT_MAX_PER_HOUR", 10),
        ),
        cursor=CursorConfig(
            api_key=_get_str(e, "CURSOR_API_KEY"),
            source_repository=_get_str(e, "CURSOR_SOURCE_REPOSITORY", "https://github.com/takak2166/KashiwaaS")
            or "https://github.com/takak2166/KashiwaaS",
            source_ref=_get_str(e, "CURSOR_SOURCE_REF", "main") or "main",
            poll_interval=_get_int(e, "CURSOR_POLL_INTERVAL", 5),
            poll_timeout=_get_int(e, "CURSOR_POLL_TIMEOUT", DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS),
            model=_get_str(e, "CURSOR_MODEL", "composer-2"),
            conversation_retry_max_retries=conv_max,
            conversation_retry_delay_seconds=conv_delay,
            conversation_text_stabilize_interval_seconds=conv_stab_interval,
            conversation_text_stabilize_required_matches=conv_stab_matches,
            conversation_text_stabilize_max_rounds=conv_stab_max,
        ),
        bot=BotConfig(
            app_token=_get_str(e, "SLACK_APP_TOKEN"),
            bot_token=_get_str(e, "SLACK_BOT_TOKEN"),
        ),
        valkey=ValkeyConfig(
            url=valkey_url,
            thread_ttl_seconds=valkey_ttl,
        ),
        mattermost=mattermost,
    )


def validate_cli_config(cfg: AppConfig, *, require_slack_credentials: bool = True) -> None:
    """
    Raise ConfigError if CLI (fetch/report) cannot run with this config.

    ``fetch --dummy`` and ``report --dry-run`` do not call the Slack API; pass
    ``require_slack_credentials=False``.
    """
    if not require_slack_credentials:
        return
    if not cfg.slack.api_token:
        raise ConfigError("SLACK_API_TOKEN is required for CLI commands")
    if not cfg.slack.channel_id:
        raise ConfigError("SLACK_CHANNEL_ID is required for CLI commands")
    if not cfg.slack.channel_name:
        raise ConfigError("SLACK_CHANNEL_NAME is required for CLI commands")
