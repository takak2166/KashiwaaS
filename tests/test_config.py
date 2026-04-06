"""Tests for AppConfig validation."""

import pytest

from src.utils.config import (
    DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS,
    MAX_VALKEY_THREAD_TTL_SECONDS,
    AlertConfig,
    AppConfig,
    BotConfig,
    ConfigError,
    CursorConfig,
    ElasticsearchConfig,
    KibanaConfig,
    SlackConfig,
    ValkeyConfig,
    load_config,
    validate_cli_config,
)


def _minimal_cfg() -> AppConfig:
    return AppConfig(
        slack=SlackConfig(api_token=None, channel_id=None, channel_name=None),
        elasticsearch=ElasticsearchConfig(host="http://localhost:9200"),
        kibana=KibanaConfig(host="http://localhost:5601"),
        selenium_host="http://localhost:4444/wd/hub",
        timezone="Asia/Tokyo",
        alert=AlertConfig(),
        cursor=CursorConfig(),
        bot=BotConfig(),
        valkey=ValkeyConfig(url="redis://localhost:6379/0"),
    )


def test_validate_cli_config_requires_slack_by_default() -> None:
    cfg = _minimal_cfg()
    with pytest.raises(ConfigError, match="SLACK_API_TOKEN"):
        validate_cli_config(cfg)


def test_validate_cli_config_skips_slack_when_disabled() -> None:
    cfg = _minimal_cfg()
    validate_cli_config(cfg, require_slack_credentials=False)


def test_load_config_cursor_poll_timeout_default() -> None:
    cfg = load_config({})
    assert cfg.cursor.poll_timeout == DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS


def test_cursor_config_poll_timeout_default() -> None:
    assert CursorConfig().poll_timeout == DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS


def test_load_config_invalid_int_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="CURSOR_POLL_INTERVAL"):
        load_config({"CURSOR_POLL_INTERVAL": "not-an-int"})


def test_load_config_invalid_float_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="CURSOR_CONVERSATION_RETRY_DELAY_SECONDS"):
        load_config({"CURSOR_CONVERSATION_RETRY_DELAY_SECONDS": "x"})


def test_load_config_valkey_ttl_negative_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="VALKEY_THREAD_TTL_SECONDS must be >= 0"):
        load_config({"VALKEY_THREAD_TTL_SECONDS": "-1"})


def test_load_config_valkey_ttl_above_max_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="VALKEY_THREAD_TTL_SECONDS must be <="):
        load_config({"VALKEY_THREAD_TTL_SECONDS": str(MAX_VALKEY_THREAD_TTL_SECONDS + 1)})
