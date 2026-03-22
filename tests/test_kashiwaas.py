"""
Tests for KashiwaaS bot handler and utilities
"""

import threading
import time
from unittest.mock import MagicMock, patch

from src.bot.kashiwaas import (
    SLACK_MARKDOWN_BLOCK_TEXT_MAX,
    _extract_question,
    _fallback_notification_text,
    _say_markdown_chunks,
    _split_message,
)
from src.bot.thread_store import ThreadStore
from src.cursor.client import AgentMessage, AgentResult, AgentStatus


class TestExtractQuestion:
    """Tests for _extract_question utility"""

    def test_single_mention(self):
        result = _extract_question("<@U12345> What is Python?")
        assert result == "What is Python?"

    def test_multiple_mentions(self):
        result = _extract_question("<@U12345> <@U67890> What is Python?")
        assert result == "What is Python?"

    def test_mention_only(self):
        result = _extract_question("<@U12345>")
        assert result == ""

    def test_empty_string(self):
        result = _extract_question("")
        assert result == ""

    def test_no_mention(self):
        result = _extract_question("What is Python?")
        assert result == "What is Python?"

    def test_mention_in_middle(self):
        result = _extract_question("Hey <@U12345> explain async")
        assert result == "Hey  explain async"


class TestSplitMessage:
    """Tests for _split_message utility"""

    def test_short_message(self):
        result = _split_message("Hello", max_length=100)
        assert result == ["Hello"]

    def test_exact_limit(self):
        text = "a" * 100
        result = _split_message(text, max_length=100)
        assert result == [text]

    def test_split_at_newline(self):
        text = "line1\nline2\nline3"
        result = _split_message(text, max_length=10)
        assert len(result) >= 2
        assert "line1" in result[0]

    def test_split_at_space(self):
        text = "word1 word2 word3"
        result = _split_message(text, max_length=10)
        assert len(result) >= 2

    def test_forced_split(self):
        text = "a" * 200
        result = _split_message(text, max_length=100)
        assert len(result) == 2
        assert len(result[0]) == 100
        assert len(result[1]) == 100

    def test_empty_message(self):
        result = _split_message("")
        assert result == [""]

    def test_split_preserves_leading_indentation(self):
        """Continuation chunk keeps leading spaces so code indentation is not lost."""
        text = "AAAAAAAAAA\n    def foo():"
        result = _split_message(text, max_length=20)
        assert len(result) == 2
        assert result[0] == "AAAAAAAAAA"
        assert result[1] == "    def foo():"

    def test_split_preserves_paragraph_breaks(self):
        """Only the single newline at the split is stripped; extra newlines preserved."""
        text = "Hi\n\n\nX"
        result = _split_message(text, max_length=3)
        assert len(result) >= 2
        # After "Hi", continuation should be "\n\nX" (one \n stripped), so second chunk starts with \n
        assert result[1].startswith("\n"), "paragraph breaks preserved in continuation chunk"

    def test_split_strips_leading_space_at_space_boundary(self):
        """When splitting at a space, the single leading space is stripped from the continuation."""
        text = "word1 word2"
        result = _split_message(text, max_length=6)
        assert len(result) == 2
        assert result[0] == "word1"
        assert result[1] == "word2"

    def test_split_uses_custom_max_length(self):
        text = "a" * 100
        result = _split_message(text, max_length=SLACK_MARKDOWN_BLOCK_TEXT_MAX)
        assert result == [text]


class TestMarkdownBlockHelpers:
    """Block Kit markdown block posting helpers."""

    def test_fallback_notification_text_truncates(self):
        long = "x" * 5000
        out = _fallback_notification_text(long)
        assert len(out) == 4000
        assert out.endswith("…")

    def test_say_markdown_chunks_posts_markdown_blocks(self):
        say = MagicMock()
        _say_markdown_chunks(say, ["# Hi\n\n**bold**"], "1.0")
        say.assert_called_once()
        kwargs = say.call_args[1]
        assert kwargs["thread_ts"] == "1.0"
        assert kwargs["blocks"] == [{"type": "markdown", "text": "# Hi\n\n**bold**"}]
        assert "text" in kwargs

    def test_say_markdown_chunks_multiple_messages(self):
        say = MagicMock()
        _say_markdown_chunks(say, ["part1", "part2"], "2.0")
        assert say.call_count == 2


class TestThreadStore:
    """Tests for ThreadStore class"""

    def test_set_and_get(self):
        store = ThreadStore()
        store.set("thread_1", "agent_1")
        assert store.get("thread_1") == "agent_1"

    def test_get_missing(self):
        store = ThreadStore()
        assert store.get("nonexistent") is None

    def test_remove(self):
        store = ThreadStore()
        store.set("thread_1", "agent_1")
        store.remove("thread_1")
        assert store.get("thread_1") is None

    def test_remove_missing(self):
        store = ThreadStore()
        store.remove("nonexistent")

    def test_overwrite(self):
        store = ThreadStore()
        store.set("thread_1", "agent_1")
        store.set("thread_1", "agent_2")
        assert store.get("thread_1") == "agent_2"

    def test_last_message_id(self):
        store = ThreadStore()
        store.set("thread_1", "agent_1")
        assert store.get_last_message_id("thread_1") is None
        store.set_last_message_id("thread_1", "msg_123")
        assert store.get_last_message_id("thread_1") == "msg_123"
        assert store.get_last_message_fingerprint("thread_1") is None
        store.set_last_message_fingerprint("thread_1", "fp_123")
        assert store.get_last_message_fingerprint("thread_1") == "fp_123"
        store.remove("thread_1")
        assert store.get("thread_1") is None
        assert store.get_last_message_id("thread_1") is None
        assert store.get_last_message_fingerprint("thread_1") is None

    def test_ttl_expiration(self):
        store = ThreadStore(ttl_seconds=0)
        store.set("thread_1", "agent_1")
        time.sleep(0.01)
        assert store.get("thread_1") is None

    def test_len(self):
        store = ThreadStore()
        assert len(store) == 0
        store.set("thread_1", "agent_1")
        store.set("thread_2", "agent_2")
        assert len(store) == 2

    def test_len_after_expiration(self):
        store = ThreadStore(ttl_seconds=0)
        store.set("thread_1", "agent_1")
        time.sleep(0.01)
        assert len(store) == 0


class TestHandleMention:
    """Tests for _handle_mention logic"""

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    def test_empty_question_replies_with_help(self, mock_store, _mock_dup):
        from src.bot.kashiwaas import _handle_mention

        ack = MagicMock()
        event = {"text": "<@U12345>", "channel": "C123", "ts": "1234.5678"}
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()

        _handle_mention(ack, event, say, client, cursor_client)

        ack.assert_called_once()
        say.assert_called_once()
        assert "Please enter a question" in say.call_args[1]["text"]
        cursor_client.ask.assert_not_called()

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    @patch("src.bot.kashiwaas.threading.Thread")
    def test_new_question_adds_eyes_reaction(self, mock_thread_class, mock_store, _mock_dup):
        from src.bot.kashiwaas import _handle_mention

        # Run _process synchronously so the test is deterministic (CI runs fast and thread may finish before assert)
        def run_target_immediately(*args, **kwargs):
            target = kwargs.get("target")
            mock_thread = MagicMock()

            def start():
                if target:
                    target()

            mock_thread.start.side_effect = start
            return mock_thread

        mock_thread_class.side_effect = run_target_immediately

        mock_store.get.return_value = None
        event = {
            "text": "<@U12345> What is Python?",
            "channel": "C123",
            "ts": "1234.5678",
        }
        ack = MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.ask.return_value = AgentResult(
            agent_id="agent_1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m1", type="assistant_message", text="Python is a language.")],
        )

        _handle_mention(ack, event, say, client, cursor_client)

        ack.assert_called_once()
        client.reactions_add.assert_any_call(channel="C123", timestamp="1234.5678", name="eyes")

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    @patch("src.bot.kashiwaas.threading.Thread")
    def test_thread_ts_used_for_reply(self, mock_thread_class, mock_store, _mock_dup):
        """When event has thread_ts, it should be used as the reply target"""
        from src.bot.kashiwaas import _handle_mention

        def run_target_immediately(*args, **kwargs):
            target = kwargs.get("target")
            mock_thread = MagicMock()

            def start():
                if target:
                    target()

            mock_thread.start.side_effect = start
            return mock_thread

        mock_thread_class.side_effect = run_target_immediately

        mock_store.get.return_value = None
        event = {
            "text": "<@U12345> followup question",
            "channel": "C123",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
        }
        ack = MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.ask.return_value = AgentResult(
            agent_id="agent_1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m1", type="assistant_message", text="Here is the answer.")],
        )

        _handle_mention(ack, event, say, client, cursor_client)

        ack.assert_called_once()
        client.reactions_add.assert_any_call(channel="C123", timestamp="1234.9999", name="eyes")

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    @patch("src.bot.kashiwaas.threading.Thread")
    def test_followup_error_clears_thread_mapping(self, mock_thread_class, mock_store, _mock_dup):
        """When followup returns ERROR, the stale agent mapping should be cleared."""
        from src.bot.kashiwaas import _handle_mention

        def run_target_immediately(*args, **kwargs):
            target = kwargs.get("target")
            mock_thread = MagicMock()

            def start():
                if target:
                    target()

            mock_thread.start.side_effect = start
            return mock_thread

        mock_thread_class.side_effect = run_target_immediately

        # Existing mapping for this thread
        mock_store.get.return_value = "agent_1"
        event = {
            "text": "<@U12345> followup question",
            "channel": "C123",
            "ts": "1234.0001",
            "thread_ts": "thread_1",
        }
        ack = MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.followup.return_value = AgentResult(
            agent_id="agent_1",
            status=AgentStatus.ERROR,
            messages=[],
        )

        _handle_mention(ack, event, say, client, cursor_client)

        ack.assert_called_once()
        # Mapping should be cleared so that future mentions can create a new agent
        mock_store.remove.assert_called_with("thread_1")


class TestThreadLocks:
    def test_thread_locks_evicted_when_unused(self):
        from src.bot import kashiwaas as botmod

        old_ttl = botmod.THREAD_LOCK_TTL_SECONDS
        try:
            # Make TTL short for test
            botmod.THREAD_LOCK_TTL_SECONDS = 0
            lock = botmod._get_thread_lock("thread_x")
            assert lock is not None

            # Trigger eviction on next access
            botmod._get_thread_lock("thread_y")

            with botmod._thread_locks_lock:
                assert "thread_x" not in botmod._thread_locks
        finally:
            botmod.THREAD_LOCK_TTL_SECONDS = old_ttl

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=True)
    def test_duplicate_event_skipped_no_reply(self, mock_dup_check):
        """When the same event is delivered again (e.g. Slack retry), we skip and do not reply."""
        from src.bot.kashiwaas import _handle_mention

        ack = MagicMock()
        event = {
            "text": "<@U12345> What is Python?",
            "channel": "C123",
            "ts": "1234.5678",
        }
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()

        _handle_mention(ack, event, say, client, cursor_client)

        ack.assert_called_once()
        mock_dup_check.assert_called_once_with("C123", "1234.5678")
        say.assert_not_called()
        client.reactions_add.assert_not_called()
        cursor_client.ask.assert_not_called()

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    def test_same_thread_processed_sequentially(self, _mock_dup):
        """Requests in the same thread_ts are processed sequentially (no concurrent followup)."""
        from src.bot.kashiwaas import _handle_mention

        started = threading.Event()
        unblock = threading.Event()
        in_flight = 0
        in_flight_lock = threading.Lock()

        def followup_side_effect(*_args, **_kwargs):
            nonlocal in_flight
            with in_flight_lock:
                in_flight += 1
                # If this ever becomes >1, we processed concurrently (bad)
                assert in_flight == 1
            started.set()
            unblock.wait(timeout=2)
            with in_flight_lock:
                in_flight -= 1
            return AgentResult(
                agent_id="agent_1",
                status=AgentStatus.FINISHED,
                messages=[AgentMessage(id="m1", type="assistant_message", text="ok")],
            )

        ack1, ack2 = MagicMock(), MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.followup.side_effect = followup_side_effect
        cursor_client.get_latest_assistant_message_obj.side_effect = lambda msgs: msgs[-1] if msgs else None

        # thread_store is global; set mapping so both calls use followup path
        from src.bot import kashiwaas as botmod

        botmod.thread_store.set("thread_1", "agent_1")

        event1 = {"text": "<@U12345> one", "channel": "C123", "ts": "1.0", "thread_ts": "thread_1"}
        event2 = {"text": "<@U12345> two", "channel": "C123", "ts": "2.0", "thread_ts": "thread_1"}

        _handle_mention(ack1, event1, say, client, cursor_client)
        _handle_mention(ack2, event2, say, client, cursor_client)

        assert started.wait(timeout=2)
        # Allow first to finish; second can then proceed
        unblock.set()
        time.sleep(0.2)

        assert cursor_client.followup.call_count == 2

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    @patch("src.bot.kashiwaas.threading.Thread")
    def test_no_assistant_message_clears_thread_mapping(self, mock_thread_class, mock_store, _mock_dup):
        """When no assistant message is returned, clear mapping so thread can recover."""
        from src.bot.kashiwaas import _handle_mention

        def run_target_immediately(*args, **kwargs):
            target = kwargs.get("target")
            mock_thread = MagicMock()

            def start():
                if target:
                    target()

            mock_thread.start.side_effect = start
            return mock_thread

        mock_thread_class.side_effect = run_target_immediately

        mock_store.get.return_value = "agent_1"
        mock_store.get_last_message_id.return_value = "m_prev"
        mock_store.get_last_message_fingerprint.return_value = None

        event = {
            "text": "<@U12345> followup question",
            "channel": "C123",
            "ts": "1234.0002",
            "thread_ts": "thread_1",
        }
        ack = MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.followup.return_value = AgentResult(
            agent_id="agent_1",
            status=AgentStatus.FINISHED,
            messages=[],  # no assistant messages
        )
        cursor_client.get_latest_assistant_message_obj.return_value = None

        _handle_mention(ack, event, say, client, cursor_client)

        mock_store.remove.assert_called_with("thread_1")

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    @patch("src.bot.kashiwaas.threading.Thread")
    def test_duplicate_assistant_message_not_sent_twice(self, mock_thread_class, mock_store, _mock_dup):
        from src.bot.kashiwaas import _handle_mention

        def run_target_immediately(*args, **kwargs):
            target = kwargs.get("target")
            mock_thread = MagicMock()

            def start():
                if target:
                    target()

            mock_thread.start.side_effect = start
            return mock_thread

        mock_thread_class.side_effect = run_target_immediately

        mock_store.get.return_value = "agent_1"
        mock_store.get_last_message_id.return_value = "m_dup"
        mock_store.get_last_message_fingerprint.return_value = None

        event = {
            "text": "<@U12345> followup question",
            "channel": "C123",
            "ts": "1234.0003",
            "thread_ts": "thread_1",
        }
        ack = MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.followup.return_value = AgentResult(
            agent_id="agent_1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m_dup", type="assistant_message", text="duplicate")],
        )
        cursor_client.get_latest_assistant_message_obj.side_effect = [
            AgentMessage(id="m_dup", type="assistant_message", text="duplicate"),
            AgentMessage(id="m_new", type="assistant_message", text="new answer"),
        ]
        cursor_client.get_conversation_after_complete.return_value = [
            AgentMessage(id="m_dup", type="assistant_message", text="duplicate"),
            AgentMessage(id="m_new", type="assistant_message", text="new answer"),
        ]

        _handle_mention(ack, event, say, client, cursor_client)

        say.assert_called()

    @patch("src.bot.kashiwaas._is_duplicate_event", return_value=False)
    @patch("src.bot.kashiwaas.thread_store")
    @patch("src.bot.kashiwaas.threading.Thread")
    def test_duplicate_assistant_message_retry_still_duplicate_returns_error(
        self, mock_thread_class, mock_store, _mock_dup
    ):
        from src.bot.kashiwaas import _handle_mention

        def run_target_immediately(*args, **kwargs):
            target = kwargs.get("target")
            mock_thread = MagicMock()

            def start():
                if target:
                    target()

            mock_thread.start.side_effect = start
            return mock_thread

        mock_thread_class.side_effect = run_target_immediately

        mock_store.get.return_value = "agent_1"
        mock_store.get_last_message_id.return_value = "m_dup"
        mock_store.get_last_message_fingerprint.return_value = None

        event = {
            "text": "<@U12345> followup question",
            "channel": "C123",
            "ts": "1234.0004",
            "thread_ts": "thread_1",
        }
        ack = MagicMock()
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()
        cursor_client.followup.return_value = AgentResult(
            agent_id="agent_1",
            status=AgentStatus.FINISHED,
            messages=[AgentMessage(id="m_dup", type="assistant_message", text="duplicate")],
        )
        cursor_client.get_latest_assistant_message_obj.side_effect = [
            AgentMessage(id="m_dup", type="assistant_message", text="duplicate"),
            AgentMessage(id="m_dup", type="assistant_message", text="duplicate"),
        ]
        cursor_client.get_conversation_after_complete.return_value = [
            AgentMessage(id="m_dup", type="assistant_message", text="duplicate"),
        ]

        _handle_mention(ack, event, say, client, cursor_client)

        say.assert_called_once()
        assert "same response content" in say.call_args[1]["text"]
