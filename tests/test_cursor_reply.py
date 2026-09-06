"""Tests for src.bot.application.cursor_reply.run_cursor_reply orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from src.bot.application.cursor_reply import fingerprint_text, run_cursor_reply
from src.bot.application.processing_state import ProcessingState
from src.bot.domain.conversation import ThreadConversation
from src.cursor.client import AgentResult, CursorAPIError, CursorTimeoutError, RunStatus


@dataclass
class InMemoryThreadConversationRepository:
    """Test double for ThreadConversationRepository (no Valkey)."""

    _data: dict[str, ThreadConversation] = field(default_factory=dict)

    def get(self, thread_key: str) -> ThreadConversation:
        return self._data.get(thread_key) or ThreadConversation.empty(thread_key)

    def save(self, convo: ThreadConversation) -> None:
        if convo.agent_id is None:
            self._data.pop(convo.thread_key, None)
            return
        self._data[convo.thread_key] = convo

    def delete(self, thread_key: str) -> None:
        self._data.pop(thread_key, None)


@dataclass
class FakeChatAdapter:
    posts_plain: list[str] = field(default_factory=list)
    posts_assistant: list[str] = field(default_factory=list)
    reacts: list[ProcessingState] = field(default_factory=list)

    def post_plain(self, text: str) -> None:
        self.posts_plain.append(text)

    def post_assistant(self, text: str) -> None:
        self.posts_assistant.append(text)

    def react(self, state: ProcessingState) -> None:
        self.reacts.append(state)


def _repo() -> InMemoryThreadConversationRepository:
    return InMemoryThreadConversationRepository()


def _adapter() -> FakeChatAdapter:
    return FakeChatAdapter()


def _client(**kwargs) -> MagicMock:
    c = MagicMock()
    c.conversation_retry_max_retries = kwargs.pop("conversation_retry_max_retries", 4)
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


class TestFingerprintText:
    def test_normalizes_crlf_and_rstrip(self) -> None:
        fp1 = fingerprint_text("hello\r\n")
        fp2 = fingerprint_text("hello\n")
        assert fp1 == fp2


class TestRunCursorReplyAskPath:
    def test_new_thread_ask_success_posts_assistant_and_checkmark(self) -> None:
        repo = _repo()
        adapter = _adapter()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            run_id="run1",
            status=RunStatus.FINISHED,
            result_text="Hello",
        )

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        cursor.ask.assert_called_once()
        assert repo.get("t1").agent_id == "ag1"
        assert adapter.posts_assistant == ["Hello"]
        assert ProcessingState.SUCCESS in adapter.reacts

    def test_error_status_removes_mapping_and_posts_error_plain(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "old", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag1",
            run_id="run_err",
            status=RunStatus.ERROR,
            result_text=None,
        )

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t1").agent_id is None
        assert len(adapter.posts_plain) == 1
        assert "error occurred" in adapter.posts_plain[0].lower()
        assert ProcessingState.FAILED in adapter.reacts

    def test_cancelled_same_as_error(self) -> None:
        repo = _repo()
        adapter = _adapter()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            run_id="run_c",
            status=RunStatus.CANCELLED,
            result_text=None,
        )

        run_cursor_reply(
            thread_key="t2",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t2").agent_id is None
        assert ProcessingState.FAILED in adapter.reacts

    def test_no_latest_message_removes_and_posts_failure(self) -> None:
        repo = _repo()
        adapter = _adapter()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            run_id="run1",
            status=RunStatus.FINISHED,
            result_text=None,
        )

        run_cursor_reply(
            thread_key="t3",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t3").agent_id is None
        assert "Failed to retrieve" in adapter.posts_plain[0]
        assert adapter.posts_assistant == []


class TestRunCursorReplyFollowupPath:
    def test_followup_when_agent_mapped(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag_exist", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag_exist",
            run_id="run2",
            status=RunStatus.FINISHED,
            result_text="More",
        )

        run_cursor_reply(
            thread_key="t1",
            question="Follow?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        cursor.followup.assert_called_once_with(
            "ag_exist",
            "Follow?",
            expected_previous_run_id=None,
            on_poll=None,
        )
        cursor.ask.assert_not_called()
        assert adapter.posts_assistant == ["More"]


class TestRunCursorReplyStaleRunId:
    def test_same_run_id_as_stored_posts_failure(self) -> None:
        repo = _repo()
        repo.save(
            ThreadConversation(
                "t1",
                "ag1",
                "same_run",
                fingerprint_text("old body"),
            )
        )

        adapter = _adapter()
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag1",
            run_id="same_run",
            status=RunStatus.FINISHED,
            result_text="duplicate body",
        )

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert "Failed to retrieve a new response" in adapter.posts_plain[0]
        assert adapter.posts_assistant == []
        assert ProcessingState.FAILED in adapter.reacts


class TestRunCursorReplyExceptions:
    def test_cursor_timeout(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.side_effect = CursorTimeoutError()

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t1").agent_id is None
        assert "poll timeout" in adapter.posts_plain[0].lower()

    @pytest.mark.parametrize("status", [401, 403])
    def test_cursor_api_auth_error_no_delete_posts_admin_message(self, status: int) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.side_effect = CursorAPIError(status, "nope")

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t1").agent_id == "ag1"
        assert "authentication" in adapter.posts_plain[0].lower()

    def test_cursor_api_500_removes_mapping(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.side_effect = CursorAPIError(500, "server")

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t1").agent_id is None

    def test_delete_failure_after_error_notifies_and_keeps_mapping(self) -> None:
        """C2: failed cleanup must surface to the user (no silent sticky agent_id)."""
        from valkey.exceptions import ValkeyError

        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.side_effect = CursorTimeoutError()
        original_delete = repo.delete

        def boom_delete(thread_key: str) -> None:
            raise ValkeyError("delete failed")

        repo.delete = boom_delete  # type: ignore[method-assign]

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        repo.delete = original_delete  # type: ignore[method-assign]
        assert repo.get("t1").agent_id == "ag1"
        assert "could not be reset" in adapter.posts_plain[0].lower()
        assert ProcessingState.FAILED in adapter.reacts

    def test_generic_exception_removes_mapping(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.side_effect = RuntimeError("boom")

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t1").agent_id is None
        assert "unexpected" in adapter.posts_plain[0].lower()

    def test_save_valkey_error_keeps_existing_mapping(self) -> None:
        """C1: persistence failure after Cursor success must not delete a healthy mapping."""
        from valkey.exceptions import ValkeyError

        repo = _repo()
        repo.save(ThreadConversation("t1", "ag_exist", None, None))
        adapter = _adapter()
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag_exist",
            run_id="run2",
            status=RunStatus.FINISHED,
            result_text="More",
        )
        original_save = repo.save

        def boom_save(convo: ThreadConversation) -> None:
            if convo.last_message_id is not None:
                raise ValkeyError("save failed")
            original_save(convo)

        repo.save = boom_save  # type: ignore[method-assign]

        run_cursor_reply(
            thread_key="t1",
            question="Follow?",
            repo=repo,
            cursor=cursor,
            adapter=adapter,
            on_poll=None,
        )

        assert repo.get("t1").agent_id == "ag_exist"
        assert adapter.posts_assistant == []
        assert ProcessingState.FAILED in adapter.reacts
        assert "storage" in adapter.posts_plain[0].lower()
