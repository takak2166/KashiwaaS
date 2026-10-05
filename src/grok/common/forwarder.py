"""HTTP forwarder to Grok routine webhook (Bearer + JSON only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from urllib.error import URLError

from src.grok.common.canonical import CanonicalInbound


@dataclass(frozen=True)
class GrokForwardResult:
    status: int
    body: bytes
    transport_error: bool = False

    def reply_text(self) -> str | None:
        """Optional synchronous reply text from Grok (tests / sync routines)."""
        if not self.body:
            return None
        try:
            payload = json.loads(self.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if isinstance(payload, dict):
            for key in ("text", "message", "reply"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None


class GrokForwarder(Protocol):
    def forward(self, payload: CanonicalInbound) -> GrokForwardResult: ...


class HttpGrokForwarder:
    def __init__(self, target_url: str, bearer_token: str, timeout_seconds: float = 60.0) -> None:
        self._target_url = target_url.strip()
        self._bearer_token = bearer_token.strip()
        self._timeout = timeout_seconds

    def forward(self, payload: CanonicalInbound) -> GrokForwardResult:
        body = json.dumps(payload.to_grok_json()).encode("utf-8")
        req = urllib.request.Request(
            self._target_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._bearer_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                try:
                    body = resp.read()
                except TimeoutError:
                    return GrokForwardResult(status=0, body=b"", transport_error=True)
                return GrokForwardResult(status=resp.status, body=body)
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
            except (TimeoutError, URLError):
                return GrokForwardResult(status=0, body=b"", transport_error=True)
            return GrokForwardResult(status=e.code, body=body)
        except (URLError, TimeoutError):
            return GrokForwardResult(status=0, body=b"", transport_error=True)
