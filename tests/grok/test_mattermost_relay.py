"""Unit tests for Mattermost → Grok relay (TAK-165)."""

from __future__ import annotations

import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from src.grok.common.canonical import CanonicalInbound
from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import GrokForwardResult
from src.grok.mattermost_relay.correlation import MattermostCorrelationStore
from src.grok.mattermost_relay.parse import parse_mm_payload, to_canonical
from src.grok.mattermost_relay.server import MattermostRelayConfig, make_handler_class, serve


@dataclass
class _RecordingForwarder:
    calls: list[CanonicalInbound]

    def forward(self, payload: CanonicalInbound) -> GrokForwardResult:
        self.calls.append(payload)
        return GrokForwardResult(status=200, body=b"{}")


def test_parse_form_and_canonical_thread_id():
    raw = urllib.parse.urlencode(
        {
            "token": "mm-tok",
            "channel_id": "ch1",
            "post_id": "p1",
            "root_id": "",
            "user_name": "alice",
            "text": "@kashiwaas hello",
            "trigger_id": "tr1",
        }
    ).encode()
    payload = parse_mm_payload(raw, "application/x-www-form-urlencoded")
    canonical = to_canonical(payload)
    assert canonical.platform == "mattermost"
    assert canonical.thread_id == "p1"
    assert canonical.text == "hello"
    assert canonical.trigger_id == "tr1"


def test_relay_auth_dedup_and_grok_json():
    forwarder = _RecordingForwarder(calls=[])
    config = MattermostRelayConfig(
        relay_shared_secret="relay-secret",
        mm_outgoing_webhook_token="mm-tok",
    )
    correlation = MattermostCorrelationStore()
    handler_cls = make_handler_class(config, forwarder, DedupeStore(3600), correlation)
    httpd = serve("127.0.0.1", 0, handler_cls)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    body = urllib.parse.urlencode(
        {
            "token": "mm-tok",
            "channel_id": "ch1",
            "post_id": "p99",
            "root_id": "root1",
            "user_name": "bob",
            "text": "hi",
        }
    ).encode()

    url = f"http://{host}:{port}/mm?secret=relay-secret"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200

    assert len(forwarder.calls) == 1
    sent = forwarder.calls[0].to_grok_json()
    assert sent["platform"] == "mattermost"
    assert sent["thread_id"] == "root1"
    assert sent["channel_id"] == "ch1"

    ctx = correlation.get("p99")
    assert ctx is not None
    assert ctx.thread_id == "root1"

    # Duplicate should not forward again.
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
    assert len(forwarder.calls) == 1

    # Wrong MM token → 401
    bad_body = urllib.parse.urlencode({"token": "wrong", "post_id": "p2"}).encode()
    bad_req = urllib.request.Request(url, data=bad_body, method="POST")
    bad_req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        urllib.request.urlopen(bad_req, timeout=5)
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError as e:
        assert e.code == 401

    httpd.shutdown()


def test_health_endpoint():
    forwarder = _RecordingForwarder(calls=[])
    config = MattermostRelayConfig(relay_shared_secret="s", mm_outgoing_webhook_token="t")
    handler_cls = make_handler_class(config, forwarder, DedupeStore(60), MattermostCorrelationStore())
    httpd = serve("127.0.0.1", 0, handler_cls)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=5) as resp:
        assert resp.read() == b"ok"
    httpd.shutdown()
