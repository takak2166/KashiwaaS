"""Tests for src.bot.cursor_reply.run_cursor_reply (ThreadStore + callback API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import fakeredis
import pytest

from src.bot.cursor_reply import fingerprint_text, run_cursor_reply
from src.bot.thread_store import ThreadStore
from src.cursor.client import AgentMessage, AgentResult, AgentStatus, CursorAPIError, CursorTimeoutError
from src.utils.config import ValkeyConfig


def _store() -> ThreadStore:
    cfg = ValkeyConfig(url="redis://ignored", thread_ttl_seconds=86400)
    return ThreadStore(cfg, client=fakeredis.FakeRedis(decode_responses=True))


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
        ts = _store()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m1", type="assistant_message", text="Hello")],
        )
        cursor.get_latest_assistant_message_obj.return_value = AgentMessage(
            id="m1", type="assistant_message", text="Hello"
        )

        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        cursor.ask.assert_called_once()
        assert ts.get("t1") == "ag1"
        post_as.assert_called_once_with("Hello")
        rr.assert_any_call("eyes")
        ra.assert_any_call("white_check_mark")

    def test_error_status_removes_mapping_and_posts_error_plain(self) -> None:
        ts = _store()
        ts.set("t1", "old")
        cursor = _client()
        cursor.followup.return_value = AgentResult(agent_id="ag1", status=AgentStatus.ERROR, messages=[])

        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert ts.get("t1") is None
        post_pl.assert_called_once()
        assert "error occurred" in post_pl.call_args[0][0].lower()
        rr.assert_any_call("eyes")
        ra.assert_any_call("x")

    def test_stopped_same_as_error(self) -> None:
        ts = _store()
        cursor = _client()
        cursor.ask.return_value = AgentResult(agent_id="ag1", status=AgentStatus.STOPPED, messages=[])

        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t2",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=MagicMock(),
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert ts.get("t2") is None
        ra.assert_any_call("x")

    def test_no_latest_message_removes_and_posts_failure(self) -> None:
        ts = _store()
        cursor = _client()
        cursor.ask.return_value = AgentResult(
            agent_id="ag1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m1", type="user_message", text="u")],
        )
        cursor.get_latest_assistant_message_obj.return_value = None

        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t3",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert ts.get("t3") is None
        assert "Failed to retrieve" in post_pl.call_args[0][0]
        post_as.assert_not_called()


class TestRunCursorReplyFollowupPath:
    def test_followup_when_agent_mapped(self) -> None:
        ts = _store()
        ts.set("t1", "ag_exist")
        cursor = _client()
        cursor.followup.return_value = AgentResult(
            agent_id="ag_exist",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m2", type="assistant_message", text="More")],
        )
        cursor.get_latest_assistant_message_obj.return_value = AgentMessage(
            id="m2", type="assistant_message", text="More"
        )

        post_as = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Follow?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=MagicMock(),
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
        ts = _store()
        ts.set("t1", "ag1")
        ts.set_last_message_id("t1", "old_msg")
        ts.set_last_message_fingerprint("t1", fingerprint_text("duplicate body"))

        cursor = _client(conversation_retry_max_retries=4)
        dup_msg = AgentMessage(id="same_id", type="assistant_message", text="duplicate body")
        fresh_msg = AgentMessage(id="new", type="assistant_message", text="fresh body")

        cursor.followup.return_value = AgentResult(agent_id="ag1", status=AgentStatus.FINISHED, messages=[dup_msg])
        cursor.get_latest_assistant_message_obj.side_effect = [dup_msg, fresh_msg]
        cursor.get_conversation_after_complete.return_value = [
            AgentMessage(id="new", type="assistant_message", text="fresh body"),
        ]

        post_as = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=post_as,
            post_plain=MagicMock(),
            react_add=ra,
            react_remove=rr,
        )

        cursor.get_conversation_after_complete.assert_called()
        post_as.assert_called_once_with("fresh body")
        ra.assert_any_call("white_check_mark")

    def test_duplicate_after_max_retries_posts_repeat_message(self) -> None:
        ts = _store()
        ts.set("t1", "ag1")
        ts.set_last_message_id("t1", "same")

        cursor = _client(conversation_retry_max_retries=2)
        msg = AgentMessage(id="same", type="assistant_message", text="x")
        cursor.followup.return_value = AgentResult(agent_id="ag1", status=AgentStatus.FINISHED, messages=[msg])
        cursor.get_latest_assistant_message_obj.return_value = msg
        cursor.get_conversation_after_complete.return_value = [msg]

        post_as = MagicMock()
        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
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
        ts = _store()
        ts.set("t1", "ag1")
        cursor = _client()
        cursor.followup.side_effect = CursorTimeoutError()

        post_pl = MagicMock()
        ra = MagicMock()
        rr = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=MagicMock(),
            post_plain=post_pl,
            react_add=ra,
            react_remove=rr,
        )

        assert ts.get("t1") is None
        assert "poll timeout" in post_pl.call_args[0][0].lower()

    @pytest.mark.parametrize("status", [401, 403])
    def test_cursor_api_auth_error_no_delete_posts_admin_message(self, status: int) -> None:
        ts = _store()
        ts.set("t1", "ag1")
        cursor = _client()
        cursor.followup.side_effect = CursorAPIError(status, "nope")

        post_pl = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=MagicMock(),
            post_plain=post_pl,
            react_add=MagicMock(),
            react_remove=MagicMock(),
        )

        assert ts.get("t1") == "ag1"
        assert "authentication" in post_pl.call_args[0][0].lower()

    def test_cursor_api_500_removes_mapping(self) -> None:
        ts = _store()
        ts.set("t1", "ag1")
        cursor = _client()
        cursor.followup.side_effect = CursorAPIError(500, "server")

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=MagicMock(),
            post_plain=MagicMock(),
            react_add=MagicMock(),
            react_remove=MagicMock(),
        )

        assert ts.get("t1") is None

    def test_generic_exception_removes_mapping(self) -> None:
        ts = _store()
        ts.set("t1", "ag1")
        cursor = _client()
        cursor.followup.side_effect = RuntimeError("boom")

        post_pl = MagicMock()

        run_cursor_reply(
            thread_store_key="t1",
            question="Q?",
            thread_store=ts,
            cursor_client=cursor,
            on_poll=None,
            post_assistant_text=MagicMock(),
            post_plain=post_pl,
            react_add=MagicMock(),
            react_remove=MagicMock(),
        )

        assert ts.get("t1") is None
        assert "unexpected" in post_pl.call_args[0][0].lower()
