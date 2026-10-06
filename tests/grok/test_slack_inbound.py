"""Unit tests for Slack Events → Grok inbound."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from unittest.mock import MagicMock

from src.grok.common.canonical import CanonicalInbound
from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import GrokForwardResult
from src.grok.mattermost_relay.correlation import OutboundReplyIdempotency
from src.grok.slack_inbound.events import event_to_canonical, is_bot_authored_event, slack_dedup_key
from src.grok.slack_inbound.reply import SlackThreadTarget, SlackWebReplier
from src.grok.slack_inbound.server import SlackInboundConfig, make_handler_class, serve


def test_outbound_reply_mark_if_absent_allows_only_one_claim():
    store = OutboundReplyIdempotency()
    key = "T1:Ev-concurrent"
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: store.mark_if_absent(key), range(32)))
    assert results.count(True) == 1
    assert results.count(False) == 31


def test_outbound_reply_completed_vs_in_flight():
    store = OutboundReplyIdempotency()
    key = "T1:Ev-state"
    assert store.mark_if_absent(key) is True
    assert store.is_completed(key) is False
    store.mark_completed(key)
    assert store.mark_if_absent(key) is False
    assert store.is_completed(key) is True
    store.forget(key)
    assert store.is_completed(key) is True
    assert store.mark_if_absent(key) is False

    key2 = "T1:Ev-release"
    assert store.mark_if_absent(key2) is True
    store.forget(key2)
    assert store.mark_if_absent(key2) is True


def test_slack_web_replier_concurrent_post_calls_slack_once():
    store = OutboundReplyIdempotency()
    replier = SlackWebReplier("xoxb-test", store)
    in_post = threading.Event()
    release_post = threading.Event()

    def _slow_post(**_kwargs: object) -> None:
        in_post.set()
        assert release_post.wait(timeout=5.0)

    replier._client = MagicMock()
    replier._client.chat_postMessage.side_effect = _slow_post
    target = SlackThreadTarget(team_id="T1", channel_id="C1", thread_ts="111.111", event_id="Ev-once")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(replier.post_thread_reply, target, "hello") for _ in range(32)]
        assert in_post.wait(timeout=5.0)
        release_post.set()
        outcomes = [f.result() for f in futures]
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 31
    replier._client.chat_postMessage.assert_called_once()


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


def _sign(secret: str, body: bytes, ts: str | None = None) -> tuple[str, str]:
    timestamp = ts or str(int(time.time()))
    basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return timestamp, f"v0={digest}"


def _post_raw(host: str, port: int, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    req = urllib.request.Request(f"http://{host}:{port}/slack/events", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


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


def test_slack_events_invalid_signature_returns_401():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="nope")
    httpd, host, port = _start_test_server(secret, forwarder)
    try:
        body = json.dumps({"type": "event_callback"}).encode()
        ts, _ = _sign(secret, body)
        status, _ = _post_raw(
            host,
            port,
            body,
            {
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=deadbeef",
            },
        )
        assert status == 401
        assert forwarder.calls == []
    finally:
        httpd.shutdown()


def test_slack_events_stale_timestamp_returns_401():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="nope")
    httpd, host, port = _start_test_server(secret, forwarder)
    try:
        body = json.dumps({"type": "event_callback"}).encode()
        old_ts = str(int(time.time()) - 10_000)
        _, sig = _sign(secret, body, ts=old_ts)
        status, _ = _post_raw(
            host,
            port,
            body,
            {
                "X-Slack-Request-Timestamp": old_ts,
                "X-Slack-Signature": sig,
            },
        )
        assert status == 401
        assert forwarder.calls == []
    finally:
        httpd.shutdown()


def test_slack_events_url_verification_echoes_challenge():
    secret = "signing-secret"
    forwarder = _MockForwarder(calls=[], reply="nope")
    httpd, host, port = _start_test_server(secret, forwarder)
    try:
        body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
        ts, sig = _sign(secret, body)
        status, resp_body = _post_raw(
            host,
            port,
            body,
            {
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert status == 200
        assert json.loads(resp_body.decode()) == {"challenge": "abc123"}
        assert forwarder.calls == []
    finally:
        httpd.shutdown()


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


class _ConcurrencyTrackingForwarder:
    def __init__(self) -> None:
        self._gate = threading.Semaphore(0)
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls: list[CanonicalInbound] = []

    def forward(self, payload: CanonicalInbound) -> GrokForwardResult:
        with self._lock:
            self.calls.append(payload)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self._gate.acquire()
        with self._lock:
            self.in_flight -= 1
        return GrokForwardResult(status=200, body=b"{}")

    def release_one(self) -> None:
        self._gate.release()


def test_slack_grok_forward_pool_caps_concurrent_workers():
    secret = "signing-secret"
    forwarder = _ConcurrencyTrackingForwarder()
    pool_workers = 2
    executor = ThreadPoolExecutor(max_workers=pool_workers, thread_name_prefix="test-grok-forward")

    handler_cls = make_handler_class(
        SlackInboundConfig(signing_secret=secret),
        forwarder,
        DedupeStore(3600),
        None,
    )
    httpd = serve("127.0.0.1", 0, handler_cls, forward_executor=executor)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        for i in range(4):
            _post_slack_event(
                secret,
                host,
                port,
                {
                    "type": "app_mention",
                    "channel": "C1",
                    "ts": f"900.{i}",
                    "user": "U1",
                    "text": "<@B> burst",
                },
                event_id=f"Ev-pool-{i}",
            )

        deadline = time.time() + 5.0
        while time.time() < deadline and forwarder.max_in_flight < pool_workers:
            time.sleep(0.02)
        assert forwarder.max_in_flight == pool_workers

        for _ in range(4):
            forwarder.release_one()

        deadline = time.time() + 5.0
        while time.time() < deadline and len(forwarder.calls) < 4:
            time.sleep(0.02)
        assert len(forwarder.calls) == 4
        assert forwarder.max_in_flight == pool_workers
    finally:
        httpd.shutdown()
        executor.shutdown(wait=True)
