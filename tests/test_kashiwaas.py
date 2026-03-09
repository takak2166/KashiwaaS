"""
Tests for KashiwaaS bot handler and utilities
"""

import time
from unittest.mock import MagicMock, patch

from src.bot.kashiwaas import _extract_question, _split_message
from src.bot.thread_store import ThreadStore


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

    @patch("src.bot.kashiwaas.thread_store")
    def test_empty_question_replies_with_help(self, mock_store):
        from src.bot.kashiwaas import _handle_mention

        event = {"text": "<@U12345>", "channel": "C123", "ts": "1234.5678"}
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()

        _handle_mention(event, say, client, cursor_client)

        say.assert_called_once()
        assert "質問を入力してください" in say.call_args[1]["text"]
        cursor_client.ask.assert_not_called()

    @patch("src.bot.kashiwaas.thread_store")
    def test_new_question_adds_eyes_reaction(self, mock_store):
        from src.bot.kashiwaas import _handle_mention

        mock_store.get.return_value = None

        event = {
            "text": "<@U12345> What is Python?",
            "channel": "C123",
            "ts": "1234.5678",
        }
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()

        _handle_mention(event, say, client, cursor_client)

        client.reactions_add.assert_called_once_with(channel="C123", timestamp="1234.5678", name="eyes")

    @patch("src.bot.kashiwaas.thread_store")
    def test_thread_ts_used_for_reply(self, mock_store):
        """When event has thread_ts, it should be used as the reply target"""
        from src.bot.kashiwaas import _handle_mention

        mock_store.get.return_value = None

        event = {
            "text": "<@U12345> followup question",
            "channel": "C123",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
        }
        say = MagicMock()
        client = MagicMock()
        cursor_client = MagicMock()

        _handle_mention(event, say, client, cursor_client)

        client.reactions_add.assert_called_once_with(channel="C123", timestamp="1234.9999", name="eyes")
