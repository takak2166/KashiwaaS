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
        mattermost=None,
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


def test_load_config_cursor_text_stabilize_env() -> None:
    cfg = load_config(
        {
            "CURSOR_CONVERSATION_TEXT_STABILIZE_INTERVAL_SECONDS": "2.5",
            "CURSOR_CONVERSATION_TEXT_STABILIZE_REQUIRED_MATCHES": "5",
            "CURSOR_CONVERSATION_TEXT_STABILIZE_MAX_ROUNDS": "10",
        }
    )
    assert cfg.cursor.conversation_text_stabilize_interval_seconds == 2.5
    assert cfg.cursor.conversation_text_stabilize_required_matches == 5
    assert cfg.cursor.conversation_text_stabilize_max_rounds == 10


def test_load_config_cursor_text_stabilize_interval_negative_raises() -> None:
    with pytest.raises(ConfigError, match="CURSOR_CONVERSATION_TEXT_STABILIZE_INTERVAL_SECONDS must be >= 0"):
        load_config({"CURSOR_CONVERSATION_TEXT_STABILIZE_INTERVAL_SECONDS": "-0.1"})


def test_load_config_cursor_text_stabilize_required_matches_below_one_raises() -> None:
    with pytest.raises(ConfigError, match="CURSOR_CONVERSATION_TEXT_STABILIZE_REQUIRED_MATCHES must be >= 1"):
        load_config({"CURSOR_CONVERSATION_TEXT_STABILIZE_REQUIRED_MATCHES": "0"})


def test_load_config_cursor_text_stabilize_max_rounds_below_one_raises() -> None:
    with pytest.raises(ConfigError, match="CURSOR_CONVERSATION_TEXT_STABILIZE_MAX_ROUNDS must be >= 1"):
        load_config({"CURSOR_CONVERSATION_TEXT_STABILIZE_MAX_ROUNDS": "0"})


def test_load_config_valkey_ttl_negative_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="VALKEY_THREAD_TTL_SECONDS must be >= 0"):
        load_config({"VALKEY_THREAD_TTL_SECONDS": "-1"})


def test_load_config_valkey_ttl_above_max_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="VALKEY_THREAD_TTL_SECONDS must be <="):
        load_config({"VALKEY_THREAD_TTL_SECONDS": str(MAX_VALKEY_THREAD_TTL_SECONDS + 1)})


def test_load_config_mattermost_partial_raises() -> None:
    with pytest.raises(ConfigError, match="MATTERMOST_URL and MATTERMOST_PAT"):
        load_config({"MATTERMOST_URL": "https://mm.example.com"})


def test_load_config_mattermost_pat_without_url_raises() -> None:
    with pytest.raises(ConfigError, match="MATTERMOST_URL and MATTERMOST_PAT"):
        load_config({"MATTERMOST_PAT": "patonly"})


def test_load_config_mattermost_full() -> None:
    cfg = load_config(
        {
            "MATTERMOST_URL": "https://mm.example.com:443",
            "MATTERMOST_PAT": "pat",
            "MATTERMOST_BOT_USER_ID": "uid1",
            "MATTERMOST_VERIFY_TLS": "false",
            "MATTERMOST_LOG_RAW_WEBSOCKET": "true",
        }
    )
    assert cfg.mattermost is not None
    assert cfg.mattermost.driver_host == "mm.example.com"
    assert cfg.mattermost.driver_port == 443
    assert cfg.mattermost.verify_tls is False
    assert cfg.mattermost.log_raw_websocket is True


def test_load_config_mattermost_url_and_pat_only() -> None:
    cfg = load_config({"MATTERMOST_URL": "https://mm.example.com", "MATTERMOST_PAT": "pat"})
    assert cfg.mattermost is not None
    assert cfg.mattermost.bot_user_id == ""


@pytest.mark.parametrize(
    ("mm_url", "match"),
    [
        ("https://", "MATTERMOST_URL must include a hostname"),
        ("http://", "MATTERMOST_URL must include a hostname"),
        ("ws://mm.example.com", "MATTERMOST_URL scheme must be http or https"),
        ("ftp://mm.example.com", "MATTERMOST_URL scheme must be http or https"),
        ("wss://mm.example.com", "MATTERMOST_URL scheme must be http or https"),
    ],
)
def test_load_config_mattermost_invalid_url_raises(mm_url: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_config(
            {
                "MATTERMOST_URL": mm_url,
                "MATTERMOST_PAT": "pat",
                "MATTERMOST_BOT_USER_ID": "uid1",
            }
        )


def test_load_config_mattermost_http_default_port() -> None:
    cfg = load_config(
        {
            "MATTERMOST_URL": "http://mm.example.com",
            "MATTERMOST_PAT": "pat",
            "MATTERMOST_BOT_USER_ID": "uid1",
        }
    )
    assert cfg.mattermost is not None
    assert cfg.mattermost.driver_scheme == "http"
    assert cfg.mattermost.driver_host == "mm.example.com"
    assert cfg.mattermost.driver_port == 8065


def test_load_config_mattermost_https_default_port() -> None:
    cfg = load_config(
        {
            "MATTERMOST_URL": "https://mm.example.com",
            "MATTERMOST_PAT": "pat",
            "MATTERMOST_BOT_USER_ID": "uid1",
        }
    )
    assert cfg.mattermost is not None
    assert cfg.mattermost.driver_scheme == "https"
    assert cfg.mattermost.driver_port == 443
