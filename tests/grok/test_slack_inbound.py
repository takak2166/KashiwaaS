"""Unit tests for Slack Events → Grok inbound (TAK-167)."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from unittest.mock import MagicMock

from src.grok.common.canonical import CanonicalInbound
from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import GrokForwardResult
from src.grok.mattermost_relay.correlation import OutboundReplyIdempotency
from src.grok.slack_inbound.events import event_to_canonical, slack_dedup_key
from src.grok.slack_inbound.reply import SlackWebReplier
from src.grok.slack_inbound.server import SlackInboundConfig, make_handler_class, serve


def test_slack_dedup_key_prefers_envelope_event_id():
    event = {"channel": "C1", "ts": "1.0"}
    assert slack_dedup_key("T1", event, envelope_event_id="Ev1") == "T1:Ev1"


def test_event_to_canonical_thread_ts():
    event = {"channel": "C1", "ts": "1.0", "thread_ts": "0.9", "user": "U1", "text": "<@BOT> hi"}
    c = event_to_canonical("T1", event)
    assert c.thread_id == "0.9"
    assert c.text == "hi"
    assert c.platform == "slack"


@dataclass
class _MockForwarder:
    calls: list[CanonicalInbound]
    reply: str | None = "answer"

    def forward(self, payload: CanonicalInbound) -> GrokForwardResult:
        self.calls.append(payload)
        body = json.dumps({"text": self.reply}).encode() if self.reply else b""
        return GrokForwardResult(status=200, body=body)


def _sign(secret: str, body: bytes) -> tuple[str, str]:
    ts = str(int(time.time()))
    basestring = f"v0:{ts}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return ts, f"v0={digest}"


def test_slack_events_forward_and_reply():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="hello from grok")
    replier = SlackWebReplier("xoxb-test", OutboundReplyIdempotency())
    replier._client = MagicMock()

    handler_cls = make_handler_class(
        SlackInboundConfig(signing_secret=secret),
        forwarder,
        DedupeStore(3600),
        replier,
    )
    httpd = serve("127.0.0.1", 0, handler_cls)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    envelope = {
        "type": "event_callback",
        "team_id": "T1",
        "event_id": "Ev42",
        "event": {
            "type": "app_mention",
            "channel": "C1",
            "ts": "111.222",
            "thread_ts": "111.111",
            "user": "U1",
            "text": "<@B> question",
        },
    }
    body = json.dumps(envelope).encode()
    ts, sig = _sign(secret, body)
    req = urllib.request.Request(f"http://{host}:{port}/slack/events", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Slack-Request-Timestamp", ts)
    req.add_header("X-Slack-Signature", sig)
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200

    assert len(forwarder.calls) == 1
    assert forwarder.calls[0].team_id == "T1"
    replier._client.chat_postMessage.assert_called_once()
    kwargs = replier._client.chat_postMessage.call_args.kwargs
    assert kwargs["thread_ts"] == "111.111"
    assert kwargs["text"] == "hello from grok"

    # Duplicate event_id should not forward or post again.
    with urllib.request.urlopen(req, timeout=5):
        pass
    assert len(forwarder.calls) == 1
    replier._client.chat_postMessage.assert_called_once()

    httpd.shutdown()
