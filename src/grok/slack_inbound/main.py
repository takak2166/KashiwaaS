"""Process entry: ``python -m src.grok.slack_inbound.main``."""

from __future__ import annotations

import logging
import os
import signal
import threading

from src.grok.common.dedup import DedupeStore
from src.grok.common.forwarder import HttpGrokForwarder
from src.grok.mattermost_relay.correlation import OutboundReplyIdempotency
from src.grok.slack_inbound.forward_pool import create_forward_executor
from src.grok.slack_inbound.reply import SlackWebReplier
from src.grok.slack_inbound.server import SlackInboundConfig, make_handler_class, serve

LOG = logging.getLogger("slack-grok-inbound")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env: {name}")
    return value


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    grok_url = _required_env("GROK_TARGET_URL")
    grok_bearer = _required_env("GROK_BEARER_TOKEN")
    signing_secret = _required_env("SLACK_SIGNING_SECRET")

    host = os.environ.get("LISTEN_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("LISTEN_PORT", "8090")))
    max_body = int(os.environ.get("MAX_BODY_BYTES", "262144"))
    dedup_ttl = int(os.environ.get("INBOUND_DEDUP_TTL_SECONDS", "86400"))

    bot_token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    replier = None
    if bot_token:
        replier = SlackWebReplier(bot_token, OutboundReplyIdempotency())

    config = SlackInboundConfig(signing_secret=signing_secret, max_body_bytes=max_body)
    forwarder = HttpGrokForwarder(grok_url, grok_bearer)
    handler_cls = make_handler_class(config, forwarder, DedupeStore(dedup_ttl), replier)
    forward_executor = create_forward_executor()
    httpd = serve(host, port, handler_cls, forward_executor=forward_executor)
    LOG.info("listening on %s:%s (slack-grok-inbound)", host, port)

    def _shutdown(_signum: int, _frame: object) -> None:
        LOG.info("shutting down")
        forward_executor.shutdown(wait=False, cancel_futures=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
