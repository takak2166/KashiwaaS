"""Bounded background pool for Grok forwards after Slack ACK."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

LOG = logging.getLogger("slack-grok-inbound")

DEFAULT_SLACK_GROK_FORWARD_MAX_WORKERS = 4

# When all workers are busy, new forwards wait in the executor's FIFO queue
# (queue-wait). The HTTP handler only calls submit() after Slack 200 ACK, so
# accept/read/ACK are not blocked by Grok latency. We do not reject+log on
# saturation in M1; tune SLACK_GROK_FORWARD_MAX_WORKERS if the queue grows.


def slack_grok_forward_max_workers() -> int:
    raw = os.environ.get(
        "SLACK_GROK_FORWARD_MAX_WORKERS",
        str(DEFAULT_SLACK_GROK_FORWARD_MAX_WORKERS),
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning("invalid SLACK_GROK_FORWARD_MAX_WORKERS=%r; using default", raw)
        return DEFAULT_SLACK_GROK_FORWARD_MAX_WORKERS
    if value < 1:
        LOG.warning("SLACK_GROK_FORWARD_MAX_WORKERS=%s must be >= 1; using default", value)
        return DEFAULT_SLACK_GROK_FORWARD_MAX_WORKERS
    return value


def create_forward_executor(max_workers: int | None = None) -> ThreadPoolExecutor:
    workers = max_workers if max_workers is not None else slack_grok_forward_max_workers()
    return ThreadPoolExecutor(max_workers=workers, thread_name_prefix="slack-grok-forward")
