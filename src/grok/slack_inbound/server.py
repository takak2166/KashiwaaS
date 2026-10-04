"""Slack Events API HTTP server (Request URL mode)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import GrokForwarder
from src.grok.slack_inbound.events import event_to_canonical, parse_slack_envelope, slack_dedup_key
from src.grok.slack_inbound.reply import SlackReplier, SlackThreadTarget
from src.grok.slack_inbound.verify import SlackSignatureError, verify_slack_signature

LOG = logging.getLogger("slack-grok-inbound")


@dataclass
class SlackInboundConfig:
    signing_secret: str
    max_body_bytes: int = 262144


class SlackInboundHandler(BaseHTTPRequestHandler):
    config: SlackInboundConfig
    forwarder: GrokForwarder
    inbound_dedup: DedupeStore
    replier: SlackReplier | None

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("request %s %s", self.command, self.path.split("?", 1)[0])

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] not in ("/slack/events", "/events"):
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > self.config.max_body_bytes:
            self.send_response(413)
            self.end_headers()
            return

        raw = self.rfile.read(length)
        try:
            verify_slack_signature(
                self.config.signing_secret,
                raw,
                self.headers.get("X-Slack-Request-Timestamp"),
                self.headers.get("X-Slack-Signature"),
            )
        except SlackSignatureError:
            self.send_response(401)
            self.end_headers()
            return

        try:
            envelope = parse_slack_envelope(raw)
        except (ValueError, json.JSONDecodeError):
            self.send_response(400)
            self.end_headers()
            return

        if envelope.get("type") == "url_verification":
            challenge = envelope.get("challenge", "")
            body = json.dumps({"challenge": challenge}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return

        if envelope.get("type") != "event_callback":
            self.send_response(200)
            self.end_headers()
            return

        team_id = str(envelope.get("team_id") or "")
        event = envelope.get("event") or {}
        if not isinstance(event, dict) or event.get("type") != "app_mention":
            self.send_response(200)
            self.end_headers()
            return

        envelope_event_id = str(envelope.get("event_id") or "") or None
        dedup_key = slack_dedup_key(team_id, event, envelope_event_id=envelope_event_id)
        if self.inbound_dedup.is_duplicate(dedup_key):
            LOG.info("duplicate slack inbound skipped key=%s", dedup_key)
            self.send_response(200)
            self.end_headers()
            return

        canonical = event_to_canonical(
            team_id,
            event,
            envelope_event_id=envelope_event_id,
            received_at=datetime.now(UTC).isoformat(),
        )
        result = self.forwarder.forward(canonical)
        if result.transport_error:
            self.inbound_dedup.forget(dedup_key)
            self.send_response(502)
            self.end_headers()
            return
        LOG.info(
            "forwarded slack inbound channel=%s ts=%s grok_status=%s",
            canonical.channel_id,
            canonical.post_id,
            result.status,
        )

        reply_text = result.reply_text()
        if reply_text and self.replier is not None:
            target = SlackThreadTarget(
                team_id=team_id,
                channel_id=canonical.channel_id,
                thread_ts=canonical.thread_id,
                event_id=str(envelope_event_id or event.get("client_msg_id") or canonical.post_id),
            )
            self.replier.post_thread_reply(target, reply_text)

        self.send_response(200)
        self.end_headers()


def make_handler_class(
    config: SlackInboundConfig,
    forwarder: GrokForwarder,
    inbound_dedup: DedupeStore,
    replier: SlackReplier | None,
) -> type[SlackInboundHandler]:
    class _Handler(SlackInboundHandler):
        pass

    _Handler.config = config
    _Handler.forwarder = forwarder
    _Handler.inbound_dedup = inbound_dedup
    _Handler.replier = replier
    return _Handler


def serve(host: str, port: int, handler_cls: type[SlackInboundHandler]) -> HTTPServer:
    return HTTPServer((host, port), handler_cls)
