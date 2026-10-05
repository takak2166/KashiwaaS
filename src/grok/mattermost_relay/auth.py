"""Relay ingress authentication (Bearer token and shared secret)."""

from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def relay_secret_authorized(handler: BaseHTTPRequestHandler, relay_shared_secret: str) -> bool:
    if not relay_shared_secret:
        return False
    parsed = urlparse(handler.path)
    for values in parse_qs(parsed.query).get("secret", []):
        if hmac.compare_digest(values, relay_shared_secret):
            return True
    auth = handler.headers.get("Authorization", "")
    if hmac.compare_digest(auth, f"Bearer {relay_shared_secret}"):
        return True
    custom = handler.headers.get("X-Relay-Secret", "")
    return hmac.compare_digest(custom, relay_shared_secret)


def mm_webhook_token_valid(payload: dict, expected_token: str) -> bool:
    if not expected_token:
        return False
    token = str(payload.get("token") or "")
    return hmac.compare_digest(token, expected_token)
