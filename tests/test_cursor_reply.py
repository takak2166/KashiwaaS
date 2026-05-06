"""Tests for src.bot.cursor_reply.run_cursor_reply orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock

import fakeredis
import pytest

from src.bot.adapters.valkey.thread_conversation_repo import ValkeyThreadConversationRepository
from src.bot.cursor_reply import fingerprint_text, run_cursor_reply
from src.bot.domain.conversation import ThreadConversation
from src.cursor.client import AgentMessage, AgentResult, AgentStatus, CursorAPIError, CursorTimeoutError
from src.utils.config import ValkeyConfig


def _repo() -> ValkeyThreadConversationRepository:
    cfg = ValkeyConfig(url="redis://ignored", thread_ttl_seconds=86400)
    return ValkeyThreadConversationRepository(cfg, client=fakeredis.FakeRedis(decode_responses=True))



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
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m1", type="assistant_message", text="Hello")],
        )
        cursor.get_latest_assistant_message_obj.return_value = AgentMessage(
            id="m1", type="assistant_message", text="Hello"
        )

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        cursor.ask.assert_called_once()
        assert repo.get("t1").agent_id == "ag1"
        post_as.assert_called_once_with("Hello")
        ra.assert_any_call("white_check_mark")

    def test_error_status_removes_mapping_and_posts_error_plain(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "old", None, None))
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.ERROR,
            messages=[],
        )

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t1").agent_id is None
        post_pl.assert_called_once()
        assert "error occurred" in post_pl.call_args[0][0].lower()
        ra.assert_any_call("x")

    def test_stopped_same_as_error(self) -> None:
        repo = _repo()
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.STOPPED,
            messages=[],
        )

        run_cursor_reply(
            thread_key="t2",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t2").agent_id is None
        ra.assert_any_call("x")

    def test_no_latest_message_removes_and_posts_failure(self) -> None:
        repo = _repo()
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m1", type="user_message", text="u")],
        )
        cursor.get_latest_assistant_message_obj.return_value = None

        run_cursor_reply(
            thread_key="t3",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t3").agent_id is None
        assert "Failed to retrieve" in post_pl.call_args[0][0]
        post_as.assert_not_called()


class TestRunCursorReplyFollowupPath:
    def test_followup_when_agent_mapped(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag_exist", None, None))
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag_exist",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m2", type="assistant_message", text="More")],
        )
        cursor.get_latest_assistant_message_obj.return_value = AgentMessage(
            id="m2", type="assistant_message", text="More"
        )

        run_cursor_reply(
            thread_key="t1",
            question="Follow?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        cursor.followup.assert_called_once_with(
            "ag_exist",
            "Follow?",
            expected_previous_message_id=None,
            on_poll=None,
        )
        cursor.ask.assert_not_called()
        post_as.assert_called_once_with("More")


class TestRunCursorReplyDuplicateRetry:
    def test_retries_then_posts_when_refresh_differs(self) -> None:
        repo = _repo()
        repo.save(
            ThreadConversation(
                "t1",
                "ag1",
                "old_msg",
                fingerprint_text("duplicate body"),
            )
        )

        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client(conversation_retry_max_retries=4)
        dup_msg = AgentMessage(id="same_id", type="assistant_message", text="duplicate body")
        fresh_msg = AgentMessage(id="new", type="assistant_message", text="fresh body")

        cursor.followup.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.FINISHED,
            messages=[dup_msg],
        )
        cursor.get_latest_assistant_message_obj.side_effect = [dup_msg, fresh_msg]
        cursor.get_conversation_after_complete.return_value = [
            AgentMessage(id="new", type="assistant_message", text="fresh body"),
        ]

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        cursor.get_conversation_after_complete.assert_called()
        post_as.assert_called_once_with("fresh body")
        ra.assert_any_call("white_check_mark")

    def test_duplicate_after_max_retries_posts_repeat_message(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", "same", None))

        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client(conversation_retry_max_retries=2)
        msg = AgentMessage(id="same", type="assistant_message", text="x")
        cursor.followup.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.FINISHED,
            messages=[msg],
        )
        cursor.get_latest_assistant_message_obj.return_value = msg
        cursor.get_conversation_after_complete.return_value = [msg]

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert "repeating" in post_pl.call_args[0][0].lower()
        post_as.assert_not_called()
        ra.assert_any_call("x")


class TestRunCursorReplyExceptions:
    def test_cursor_timeout(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.followup.side_effect = CursorTimeoutError()

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t1").agent_id is None
        assert "poll timeout" in post_pl.call_args[0][0].lower()

    @pytest.mark.parametrize("status", [401, 403])
    def test_cursor_api_auth_error_no_delete_posts_admin_message(self, status: int) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.followup.side_effect = CursorAPIError(status, "nope")

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t1").agent_id == "ag1"
        assert "authentication" in post_pl.call_args[0][0].lower()

    def test_cursor_api_500_removes_mapping(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.followup.side_effect = CursorAPIError(500, "server")

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t1").agent_id is None

    def test_generic_exception_removes_mapping(self) -> None:
        repo = _repo()
        repo.save(ThreadConversation("t1", "ag1", None, None))
        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()
        cursor = _client()
        cursor.followup.side_effect = RuntimeError("boom")

        run_cursor_reply(
            thread_key="t1",
            question="Q?",
            repo=repo,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert repo.get("t1").agent_id is None
        assert "unexpected" in post_pl.call_args[0][0].lower()
