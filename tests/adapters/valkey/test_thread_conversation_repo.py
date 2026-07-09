"""Tests for Valkey-backed ThreadConversationRepository."""

from __future__ import annotations

import time

import fakeredis

from src.bot.adapters.valkey.thread_conversation_repo import ValkeyThreadConversationRepository
from src.bot.domain.conversation import ThreadConversation
from src.utils.config import ValkeyConfig


def _repo_for_test(*, thread_ttl_seconds: int = 86400, key_prefix: str = "") -> ValkeyThreadConversationRepository:
    cfg = ValkeyConfig(url="redis://ignored", thread_ttl_seconds=thread_ttl_seconds)
    return ValkeyThreadConversationRepository(
        cfg, client=fakeredis.FakeRedis(decode_responses=True), key_prefix=key_prefix
    )


def _thread_key_count(repo: ValkeyThreadConversationRepository) -> int:
    pattern = f"{repo.KEY_PREFIX}{repo._key_prefix_suffix}*"  # noqa: SLF001
    return sum(1 for _ in repo._client.scan_iter(match=pattern, count=100))


class TestValkeyThreadConversationRepository:
    def test_save_and_get_roundtrip(self) -> None:
        repo = _repo_for_test()
        conv = ThreadConversation("thread_1", "agent_1", None, None)
        repo.save(conv)
        got = repo.get("thread_1")
        assert got.agent_id == "agent_1"
        assert got.last_message_id is None

    def test_get_missing(self) -> None:
        repo = _repo_for_test()
        assert repo.get("nonexistent") == ThreadConversation.empty("nonexistent")

    def test_delete(self) -> None:
        repo = _repo_for_test()
        repo.save(ThreadConversation("thread_1", "agent_1", None, None))
        repo.delete("thread_1")
        assert repo.get("thread_1").agent_id is None

    def test_overwrite_agent_clears_last_fields_via_domain_then_save(self) -> None:
        repo = _repo_for_test()
        c1 = ThreadConversation("thread_1", "agent_1", "m1", "fp1")
        repo.save(c1)
        c2 = ThreadConversation.empty("thread_1").with_agent("agent_2")
        repo.save(c2)
        got = repo.get("thread_1")
        assert got.agent_id == "agent_2"
        assert got.last_message_id is None
        assert got.last_fingerprint is None

    def test_expire_on_save(self) -> None:
        repo = _repo_for_test(thread_ttl_seconds=10)
        repo.save(ThreadConversation("thread_1", "agent_1", None, None))
        key = repo._key("thread_1")  # noqa: SLF001
        ttl = repo._client.ttl(key)  # noqa: SLF001
        assert ttl is not None and ttl > 0

    def test_last_reply_fields(self) -> None:
        repo = _repo_for_test()
        repo.save(ThreadConversation("thread_1", "agent_1", None, None))
        repo.save(ThreadConversation("thread_1", "agent_1", "msg_123", "fp_123"))
        got = repo.get("thread_1")
        assert got.last_message_id == "msg_123"
        assert got.last_fingerprint == "fp_123"

    def test_key_prefix_namespace(self) -> None:
        slack_r = _repo_for_test(key_prefix="")
        mm_r = _repo_for_test(key_prefix="mm:")
        slack_r.save(ThreadConversation("t", "a1", None, None))
        mm_r.save(ThreadConversation("t", "a2", None, None))
        assert slack_r.get("t").agent_id == "a1"
        assert mm_r.get("t").agent_id == "a2"

    def test_ttl_expiration(self) -> None:
        repo = _repo_for_test(thread_ttl_seconds=1)
        repo.save(ThreadConversation("thread_1", "agent_1", None, None))
        time.sleep(2.0)
        assert repo.get("thread_1").agent_id is None

    def test_len_via_scan(self) -> None:
        repo = _repo_for_test()
        assert _thread_key_count(repo) == 0
        repo.save(ThreadConversation("thread_1", "agent_1", None, None))
        repo.save(ThreadConversation("thread_2", "agent_2", None, None))
        assert _thread_key_count(repo) == 2

    def test_save_uses_single_pipeline_execute(self) -> None:
        repo = _repo_for_test()
        execute_calls: list[int] = []

        real_pipeline = repo._client.pipeline

        def tracked_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
            p = real_pipeline(*args, **kwargs)
            orig_execute = p.execute

            def ex(*a, **kw):
                execute_calls.append(1)
                return orig_execute(*a, **kw)

            p.execute = ex  # type: ignore[method-assign]
            return p

        repo._client.pipeline = tracked_pipeline  # type: ignore[method-assign]
        repo.save(ThreadConversation("k", "ag", "m", "f"))

        assert sum(execute_calls) == 1
