"""Unit tests for Slack request signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from src.grok.slack_inbound.verify import SlackSignatureError, verify_slack_signature


def _sign(secret: str, body: bytes, ts: str | None = None) -> tuple[str, str]:
    timestamp = ts or str(int(time.time()))
    basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return timestamp, f"v0={digest}"


def test_verify_accepts_valid_utf8_body():
    secret = "test-secret"
    body = b'{"type":"url_verification"}'
    ts, sig = _sign(secret, body)
    verify_slack_signature(secret, body, ts, sig)


def test_verify_accepts_non_utf8_body_with_matching_signature():
    secret = "test-secret"
    body = b"\xff\xfe not utf-8"
    ts, sig = _sign(secret, body)
    verify_slack_signature(secret, body, ts, sig)


def test_verify_non_utf8_body_wrong_signature_raises_not_unicode_error():
    secret = "test-secret"
    body = b"\xff\xfe"
    ts, _ = _sign(secret, body)
    with pytest.raises(SlackSignatureError, match="signature mismatch"):
        verify_slack_signature(secret, body, ts, "v0=deadbeef")


def test_verify_rejects_stale_timestamp():
    secret = "test-secret"
    body = b"{}"
    old_ts = str(int(time.time()) - 10_000)
    _, sig = _sign(secret, body, ts=old_ts)
    with pytest.raises(SlackSignatureError, match="stale timestamp"):
        verify_slack_signature(secret, body, old_ts, sig, max_age_seconds=300)
