"""Process entry: ``python -m src.grok.mattermost_relay.main``."""

from __future__ import annotations

import logging
import os
import signal
import threading

from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import HttpGrokForwarder
from src.grok.common.target_url import grok_target_url_from_env
from src.grok.mattermost_relay.correlation import MattermostCorrelationStore
from src.grok.mattermost_relay.server import MattermostRelayConfig, make_handler_class, serve

LOG = logging.getLogger("mm-grok-relay")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env: {name}")
    return value


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    grok_url = grok_target_url_from_env(LOG)
    grok_bearer = _required_env("GROK_BEARER_TOKEN")
    relay_secret = _required_env("RELAY_SHARED_SECRET")
    mm_token = _required_env("MM_OUTGOING_WEBHOOK_TOKEN")

    host = os.environ.get("LISTEN_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("LISTEN_PORT", "8080")))
    max_body = int(os.environ.get("MAX_BODY_BYTES", "262144"))
    dedup_ttl = int(os.environ.get("INBOUND_DEDUP_TTL_SECONDS", "86400"))

    config = MattermostRelayConfig(
        relay_shared_secret=relay_secret,
        mm_outgoing_webhook_token=mm_token,
        max_body_bytes=max_body,
    )
    forwarder = HttpGrokForwarder(grok_url, grok_bearer)
    handler_cls = make_handler_class(
        config,
        forwarder,
        DedupeStore(dedup_ttl),
        MattermostCorrelationStore(),
    )
    httpd = serve(host, port, handler_cls)
    LOG.info("listening on %s:%s (mm-grok-relay)", host, port)

    def _shutdown(_signum: int, _frame: object) -> None:
        LOG.info("shutting down")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
