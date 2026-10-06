"""Regression: in-memory TTL stores use monotonic clocks, not wall time."""

from __future__ import annotations

import time

import pytest

from src.grok.common.dedup import DedupeStore
from src.grok.mattermost_relay.correlation import (
    MattermostCorrelationStore,
    MattermostRoutingContext,
    OutboundReplyIdempotency,
)


@pytest.fixture
def mono_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    t: list[float] = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: t[0])
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    return t


def test_dedupe_store_expires_on_monotonic_elapsed(mono_clock: list[float]) -> None:
    store = DedupeStore(ttl_seconds=60)
    assert store.is_duplicate("k") is False
    assert store.is_duplicate("k") is True
    mono_clock[0] = 61.0
    assert store.is_duplicate("k") is False


def test_dedupe_store_ignores_wall_clock_jump(
    monkeypatch: pytest.MonkeyPatch, mono_clock: list[float]
) -> None:
    wall = [1_700_000_000.0]
    monkeypatch.setattr(time, "time", lambda: wall[0])
    store = DedupeStore(ttl_seconds=60)
    assert store.is_duplicate("k") is False
    mono_clock[0] = 1.0
    wall[0] = 9_999_999_999.0
    assert store.is_duplicate("k") is True


def test_correlation_store_expires_on_monotonic_elapsed(mono_clock: list[float]) -> None:
    store = MattermostCorrelationStore(ttl_seconds=60)
    ctx = MattermostRoutingContext(channel_id="c", thread_id="t", post_id="p1")
    store.put(ctx)
    assert store.get("p1") == ctx
    mono_clock[0] = 61.0
    assert store.get("p1") is None


def test_outbound_idempotency_expires_on_monotonic_elapsed(mono_clock: list[float]) -> None:
    store = OutboundReplyIdempotency(ttl_seconds=60)
    assert store.mark_if_absent("key") is True
    assert store.mark_if_absent("key") is False
    mono_clock[0] = 61.0
    assert store.mark_if_absent("key") is True
