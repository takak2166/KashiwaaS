"""Unit tests for Slack Events → Grok inbound."""

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
from src.grok.slack_inbound.events import event_to_canonical, is_bot_authored_event, slack_dedup_key
from src.grok.slack_inbound.reply import SlackWebReplier
from src.grok.slack_inbound.server import SlackInboundConfig, make_handler_class, serve


def test_slack_dedup_key_prefers_envelope_event_id():
    event = {"channel": "C1", "ts": "1.0"}
    assert slack_dedup_key("T1", event, envelope_event_id="Ev1") == "T1:Ev1"


def test_is_bot_authored_event():
    assert is_bot_authored_event({"bot_id": "B123"})
    assert is_bot_authored_event({"subtype": "bot_message"})
    assert not is_bot_authored_event({"subtype": "thread_broadcast"})
    assert not is_bot_authored_event({"user": "U1"})


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

    deadline = time.time() + 5.0
    while time.time() < deadline and len(forwarder.calls) < 1:
        time.sleep(0.05)

    assert len(forwarder.calls) == 1
    assert forwarder.calls[0].team_id == "T1"
    deadline = time.time() + 5.0
    while time.time() < deadline and replier._client.chat_postMessage.call_count < 1:
        time.sleep(0.05)
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


def _post_slack_event(
    secret: str,
    host: str,
    port: int,
    event: dict,
    *,
    event_id: str = "Ev-bot-filter",
) -> None:
    envelope = {
        "type": "event_callback",
        "team_id": "T1",
        "event_id": event_id,
        "event": event,
    }
    body = json.dumps(envelope).encode()
    ts, sig = _sign(secret, body)
    req = urllib.request.Request(f"http://{host}:{port}/slack/events", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Slack-Request-Timestamp", ts)
    req.add_header("X-Slack-Signature", sig)
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


def _start_test_server(secret: str, forwarder: _MockForwarder):
    handler_cls = make_handler_class(
        SlackInboundConfig(signing_secret=secret),
        forwarder,
        DedupeStore(3600),
        None,
    )
    httpd = serve("127.0.0.1", 0, handler_cls)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, host, port


def test_slack_events_skip_bot_id():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="nope")
    httpd, host, port = _start_test_server(secret, forwarder)
    try:
        _post_slack_event(
            secret,
            host,
            port,
            {
                "type": "app_mention",
                "bot_id": "B999",
                "channel": "C1",
                "ts": "222.333",
                "text": "<@BOT> from bot",
            },
            event_id="Ev-bot-id",
        )
        time.sleep(0.3)
        assert forwarder.calls == []
    finally:
        httpd.shutdown()


def test_slack_events_skip_bot_message_subtype():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="nope")
    httpd, host, port = _start_test_server(secret, forwarder)
    try:
        _post_slack_event(
            secret,
            host,
            port,
            {
                "type": "app_mention",
                "subtype": "bot_message",
                "channel": "C1",
                "ts": "333.444",
                "text": "<@BOT> bot subtype",
            },
            event_id="Ev-bot-subtype",
        )
        time.sleep(0.3)
        assert forwarder.calls == []
    finally:
        httpd.shutdown()


def test_slack_events_thread_broadcast_still_forwards():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="ok")
    httpd, host, port = _start_test_server(secret, forwarder)
    try:
        _post_slack_event(
            secret,
            host,
            port,
            {
                "type": "app_mention",
                "subtype": "thread_broadcast",
                "channel": "C1",
                "ts": "444.555",
                "user": "U1",
                "text": "<@BOT> broadcast",
            },
            event_id="Ev-thread-broadcast",
        )
        deadline = time.time() + 5.0
        while time.time() < deadline and len(forwarder.calls) < 1:
            time.sleep(0.05)
        assert len(forwarder.calls) == 1
    finally:
        httpd.shutdown()


class _FlakyReplier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_next = True

    def post_thread_reply(self, target, text: str) -> bool:
        self.calls.append((target.channel_id, text))
        if self._fail_next:
            self._fail_next = False
            return False
        return True


def test_slack_reply_failure_keeps_dedup_and_retries_reply_only():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="grok answer")
    replier = _FlakyReplier()

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
        "event_id": "Ev-reply-retry",
        "event": {
            "type": "app_mention",
            "channel": "C1",
            "ts": "555.666",
            "thread_ts": "555.555",
            "user": "U1",
            "text": "<@B> retry me",
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

    deadline = time.time() + 5.0
    while time.time() < deadline and len(forwarder.calls) < 1:
        time.sleep(0.05)
    assert len(forwarder.calls) == 1
    deadline = time.time() + 5.0
    while time.time() < deadline and len(replier.calls) < 1:
        time.sleep(0.05)
    assert len(replier.calls) == 1

    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200

    deadline = time.time() + 5.0
    while time.time() < deadline and len(replier.calls) < 2:
        time.sleep(0.05)
    assert len(forwarder.calls) == 1
    assert len(replier.calls) == 2
    assert replier.calls[0] == replier.calls[1]

    httpd.shutdown()
