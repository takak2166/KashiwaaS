"""HTTP server for Mattermost → Grok relay."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.grok.common.content_length import parse_content_length
from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import GrokForwarder
from src.grok.mattermost_relay.auth import mm_webhook_token_valid, relay_secret_authorized
from src.grok.mattermost_relay.correlation import MattermostCorrelationStore, MattermostRoutingContext
from src.grok.mattermost_relay.parse import parse_mm_payload, to_canonical

LOG = logging.getLogger("mm-grok-relay")


@dataclass
class MattermostRelayConfig:
    relay_shared_secret: str
    mm_outgoing_webhook_token: str
    max_body_bytes: int = 262144


class MattermostRelayHandler(BaseHTTPRequestHandler):
    config: MattermostRelayConfig
    forwarder: GrokForwarder
    inbound_dedup: DedupeStore
    correlation: MattermostCorrelationStore

    def log_message(self, fmt: str, *args: Any) -> None:
        # Avoid default access logs that may include query secrets.
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
        path = self.path.split("?", 1)[0]
        if path not in ("/mm", "/webhook", "/"):
            self._respond(404, b"")
            return

        if not relay_secret_authorized(self, self.config.relay_shared_secret):
            self._respond(401, b"unauthorized")
            return

        length = parse_content_length(self.headers.get("Content-Length"))
        if length is None:
            self._respond(400, b"bad request")
            return
        if length > self.config.max_body_bytes:
            self._respond(413, b"payload too large")
            return

        raw = self.rfile.read(length)
        try:
            payload = parse_mm_payload(raw, self.headers.get("Content-Type"))
        except (ValueError, UnicodeDecodeError) as e:
            LOG.warning("invalid mm payload: %s", type(e).__name__)
            self._respond(400, b"bad request")
            return

        if not mm_webhook_token_valid(payload, self.config.mm_outgoing_webhook_token):
            self._respond(401, b"unauthorized")
            return

        canonical = to_canonical(payload, received_at=datetime.now(UTC).isoformat())
        if not canonical.post_id:
            self._respond(400, b"missing post_id")
            return

        dedup_key = canonical.post_id
        if canonical.trigger_id:
            dedup_key = f"{canonical.post_id}:{canonical.trigger_id}"

        if self.inbound_dedup.is_duplicate(dedup_key):
            LOG.info("duplicate mm inbound skipped post_id=%s", canonical.post_id)
            self._respond(200, b"")
            return

        result = self.forwarder.forward(canonical)
        if result.transport_error or not (200 <= result.status < 300):
            self.inbound_dedup.forget(dedup_key)
            upstream = 502 if result.transport_error else result.status
            self._respond(upstream, b"")
            return

        self.correlation.put(
            MattermostRoutingContext(
                channel_id=canonical.channel_id,
                thread_id=canonical.thread_id,
                post_id=canonical.post_id,
            )
        )
        LOG.info(
            "forwarded mm inbound post_id=%s grok_status=%s",
            canonical.post_id,
            result.status,
        )
        # MM webhook must not carry user-visible chat reply in the response body.
        self._respond(200, b"")

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.end_headers()
        if body:
            self.wfile.write(body)


def make_handler_class(
    config: MattermostRelayConfig,
    forwarder: GrokForwarder,
    inbound_dedup: DedupeStore,
    correlation: MattermostCorrelationStore,
) -> type[MattermostRelayHandler]:
    class _Handler(MattermostRelayHandler):
        pass

    _Handler.config = config
    _Handler.forwarder = forwarder
    _Handler.inbound_dedup = inbound_dedup
    _Handler.correlation = correlation
    return _Handler


def serve(
    host: str,
    port: int,
    handler_cls: type[MattermostRelayHandler],
) -> HTTPServer:
    return HTTPServer((host, port), handler_cls)
