"""Slack request signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time


class SlackSignatureError(Exception):
    pass


def verify_slack_signature(
    signing_secret: str,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    *,
    max_age_seconds: int = 300,
) -> None:
    if not signing_secret:
        raise SlackSignatureError("missing signing secret")
    if not timestamp_header or not signature_header:
        raise SlackSignatureError("missing slack signature headers")
    try:
        ts = int(timestamp_header)
    except ValueError:
        raise SlackSignatureError("invalid timestamp") from None
    if abs(time.time() - ts) > max_age_seconds:
        raise SlackSignatureError("stale timestamp")

    basestring = f"v0:{timestamp_header}:{body.decode('utf-8')}"
    digest = hmac.new(signing_secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    if not hmac.compare_digest(expected, signature_header):
        raise SlackSignatureError("signature mismatch")
