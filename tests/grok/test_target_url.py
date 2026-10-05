"""Unit tests for GROK_TARGET_URL startup validation."""

from __future__ import annotations

import logging

import pytest

from src.grok.common.target_url import grok_target_url_from_env, validate_grok_target_url


def test_validate_https_ok():
    assert validate_grok_target_url("https://grok.example/hook") == "https://grok.example/hook"


def test_validate_http_without_opt_in_exits():
    with pytest.raises(SystemExit, match="GROK_ALLOW_INSECURE_HTTP"):
        validate_grok_target_url("http://grok.example/hook")


def test_validate_http_with_opt_in_warns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setenv("GROK_ALLOW_INSECURE_HTTP", "1")
    log = logging.getLogger("test-grok-url")
    with caplog.at_level(logging.WARNING):
        assert validate_grok_target_url("http://grok.example/hook", log) == "http://grok.example/hook"
    assert "cleartext" in caplog.text


def test_validate_missing_hostname_exits():
    with pytest.raises(SystemExit, match="hostname"):
        validate_grok_target_url("https://")


def test_validate_bad_scheme_exits():
    with pytest.raises(SystemExit, match="http or https"):
        validate_grok_target_url("ftp://grok.example/hook")


def test_grok_target_url_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROK_TARGET_URL", "https://grok.example/routine")
    assert grok_target_url_from_env() == "https://grok.example/routine"


def test_grok_target_url_from_env_missing_exits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GROK_TARGET_URL", raising=False)
    with pytest.raises(SystemExit, match="Missing required env"):
        grok_target_url_from_env()
