"""Slack Events API HTTP server (Request URL mode)."""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.grok.common.content_length import parse_content_length
from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import GrokForwarder
from src.grok.common.request_body import (
    DEFAULT_REQUEST_BODY_READ_TIMEOUT_SECONDS,
    RequestBodyReadTimeoutError,
    read_request_body,
)
from src.grok.slack_inbound.events import (
    event_to_canonical,
    is_bot_authored_event,
    parse_slack_envelope,
    slack_dedup_key,
)
from src.grok.slack_inbound.forward_pool import create_forward_executor
from src.grok.slack_inbound.pending_reply import PendingSlackReply, PendingSlackReplyStore
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
    pending_replies: PendingSlackReplyStore
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

        length = parse_content_length(self.headers.get("Content-Length"))
        if length is None:
            self.send_response(400)
            self.end_headers()
            return
        if length > self.config.max_body_bytes:
            self.send_response(413)
            self.end_headers()
            return

        read_timeout = getattr(
            self.server,
            "request_body_read_timeout",
            DEFAULT_REQUEST_BODY_READ_TIMEOUT_SECONDS,
        )
        try:
            raw = read_request_body(self.rfile, self.connection, length, read_timeout)
        except RequestBodyReadTimeoutError:
            self.send_response(408)
            self.end_headers()
            return
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

        if is_bot_authored_event(event):
            LOG.info("bot-authored slack inbound skipped channel=%s ts=%s", event.get("channel"), event.get("ts"))
            self.send_response(200)
            self.end_headers()
            return

        envelope_event_id = str(envelope.get("event_id") or "") or None
        dedup_key = slack_dedup_key(team_id, event, envelope_event_id=envelope_event_id)
        if self.inbound_dedup.is_duplicate(dedup_key):
            LOG.info("duplicate slack inbound key=%s", dedup_key)
            pending = self.pending_replies.get(dedup_key)
            if pending is not None and self.replier is not None:
                handler = self

                def _retry_slack_reply_only() -> None:
                    if handler.replier.post_thread_reply(pending.target, pending.text):
                        handler.pending_replies.forget(dedup_key)
                    else:
                        LOG.warning("slack thread reply retry failed key=%s", dedup_key)

                threading.Thread(target=_retry_slack_reply_only, daemon=True).start()
            self.send_response(200)
            self.end_headers()
            return

        canonical = event_to_canonical(
            team_id,
            event,
            envelope_event_id=envelope_event_id,
            received_at=datetime.now(UTC).isoformat(),
        )

        self.send_response(200)
        self.end_headers()

        handler = self

        def _process_grok_inbound() -> None:
            try:
                result = handler.forwarder.forward(canonical)
                if result.transport_error or not (200 <= result.status < 300):
                    handler.inbound_dedup.forget(dedup_key)
                    LOG.error(
                        "grok forward failed after slack ack event_id=%s key=%s transport=%s status=%s",
                        envelope_event_id or "",
                        dedup_key,
                        result.transport_error,
                        result.status,
                    )
                    return
                LOG.info(
                    "forwarded slack inbound channel=%s ts=%s grok_status=%s",
                    canonical.channel_id,
                    canonical.post_id,
                    result.status,
                )

                reply_text = result.reply_text()
                if reply_text and handler.replier is not None:
                    target = SlackThreadTarget(
                        team_id=team_id,
                        channel_id=canonical.channel_id,
                        thread_ts=canonical.thread_id,
                        event_id=str(envelope_event_id or event.get("client_msg_id") or canonical.post_id),
                    )
                    handler.pending_replies.put(dedup_key, PendingSlackReply(target=target, text=reply_text))
                    if handler.replier.post_thread_reply(target, reply_text):
                        handler.pending_replies.forget(dedup_key)
                    else:
                        LOG.warning(
                            "slack thread reply failed key=%s channel=%s thread_ts=%s",
                            dedup_key,
                            canonical.channel_id,
                            canonical.thread_id,
                        )
            except Exception:
                handler.inbound_dedup.forget(dedup_key)
                LOG.exception(
                    "unexpected error processing slack inbound after ack event_id=%s key=%s",
                    envelope_event_id or "",
                    dedup_key,
                )

        executor: ThreadPoolExecutor | None = getattr(self.server, "forward_executor", None)
        if executor is None:
            executor = create_forward_executor()
            self.server.forward_executor = executor
        try:
            executor.submit(_process_grok_inbound)
        except RuntimeError:
            handler.inbound_dedup.forget(dedup_key)
            LOG.error(
                "grok forward rejected: executor shut down event_id=%s key=%s",
                envelope_event_id or "",
                dedup_key,
            )


def make_handler_class(
    config: SlackInboundConfig,
    forwarder: GrokForwarder,
    inbound_dedup: DedupeStore,
    replier: SlackReplier | None,
    pending_replies: PendingSlackReplyStore | None = None,
) -> type[SlackInboundHandler]:
    class _Handler(SlackInboundHandler):
        pass

    _Handler.config = config
    _Handler.forwarder = forwarder
    _Handler.inbound_dedup = inbound_dedup
    _Handler.pending_replies = pending_replies or PendingSlackReplyStore()
    _Handler.replier = replier
    return _Handler


def serve(
    host: str,
    port: int,
    handler_cls: type[SlackInboundHandler],
    request_body_read_timeout: float = DEFAULT_REQUEST_BODY_READ_TIMEOUT_SECONDS,
    forward_executor: ThreadPoolExecutor | None = None,
) -> HTTPServer:
    httpd = HTTPServer((host, port), handler_cls)
    httpd.request_body_read_timeout = request_body_read_timeout
    httpd.forward_executor = forward_executor or create_forward_executor()
    return httpd
