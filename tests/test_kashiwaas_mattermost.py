"""Tests for Mattermost KashiwaaS bot helpers and handler wiring."""

import json
import ssl
from unittest.mock import MagicMock, patch

import pytest

from src.bot import kashiwaas_mattermost as mm_bot
from src.bot.kashiwaas_mention import (
    MattermostPostedEvent,
    extract_question_mattermost,
    format_kashiwaas_help_reply,
    is_help_only_question,
    mattermost_broadcast_mentions_bot,
    mattermost_post_mentions_bot,
    mattermost_posted_event_from_broadcast,
    mattermost_root_post_id,
)
from src.cursor.client import AgentMessage, AgentResult, AgentStatus
from src.utils.config import ConfigError, MattermostConfig


def test_mattermost_wss_ssl_context_verify_on() -> None:
    ctx = mm_bot._mattermost_wss_ssl_context(True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_mattermost_wss_ssl_context_verify_off() -> None:
    ctx = mm_bot._mattermost_wss_ssl_context(False)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_resolve_mattermost_bot_user_id_from_pat() -> None:
    driver = MagicMock()
    driver.client.userid = "mm-real-id"
    mm_cfg = MattermostConfig(
        url="https://mm.example.com",
        pat="pat",
        bot_user_id="",
        driver_scheme="https",
        driver_host="mm.example.com",
        driver_port=443,
    )
    out = mm_bot._resolve_mattermost_bot_user_id(mm_cfg, driver)
    assert out.bot_user_id == "mm-real-id"


def test_resolve_mattermost_bot_user_id_env_must_match_pat() -> None:
    driver = MagicMock()
    driver.client.userid = "mm-real-id"
    mm_cfg = MattermostConfig(
        url="https://mm.example.com",
        pat="pat",
        bot_user_id="wrong-id",
        driver_scheme="https",
        driver_host="mm.example.com",
        driver_port=443,
    )
    with pytest.raises(ConfigError, match="does not match"):
        mm_bot._resolve_mattermost_bot_user_id(mm_cfg, driver)


def test_resolve_mattermost_bot_user_id_empty_api_raises() -> None:
    driver = MagicMock()
    driver.client.userid = ""
    mm_cfg = MattermostConfig(
        url="https://mm.example.com",
        pat="pat",
        bot_user_id="",
        driver_scheme="https",
        driver_host="mm.example.com",
        driver_port=443,
    )
    with pytest.raises(ConfigError, match="did not return a user id"):
        mm_bot._resolve_mattermost_bot_user_id(mm_cfg, driver)


def test_mattermost_root_post_id_thread_reply() -> None:
    assert mattermost_root_post_id({"id": "child", "root_id": "root1"}) == "root1"


def test_mattermost_root_post_id_top_level() -> None:
    assert mattermost_root_post_id({"id": "p1", "root_id": ""}) == "p1"


def test_extract_question_mattermost() -> None:
    uid = "abc123"
    q = extract_question_mattermost(f"@{uid} what is asyncio?", uid)
    assert q == "what is asyncio?"


def test_extract_question_mattermost_strips_username_mention() -> None:
    uid = "botuserid"
    q = extract_question_mattermost("@kashiwaas hello there", uid, bot_username="kashiwaas")
    assert q == "hello there"


def test_extract_question_mattermost_username_same_as_id_no_double_strip() -> None:
    uid = "same"
    q = extract_question_mattermost("@same hi", uid, bot_username="same")
    assert q == "hi"


def test_is_help_only_question() -> None:
    assert is_help_only_question("help") is True
    assert is_help_only_question("HELP!") is True
    assert is_help_only_question("help me") is True
    assert is_help_only_question("?") is True
    assert is_help_only_question("？") is True
    assert is_help_only_question("how do I use help in python") is False


def test_format_kashiwaas_help_reply_contains_example() -> None:
    body = format_kashiwaas_help_reply(example_line="`@x hi`")
    assert "`@x hi`" in body
    assert "help" in body.lower()


def test_mattermost_post_mentions_bot_by_at_id() -> None:
    uid = "u1"
    assert mattermost_post_mentions_bot({"message": f"hello @{uid} there"}, uid) is True


def test_mattermost_post_mentions_bot_by_at_configured_username() -> None:
    uid = "longid"
    assert mattermost_post_mentions_bot(
        {"message": "@kashiwaas ping"},
        uid,
        bot_username="kashiwaas",
    ) is True


def test_mattermost_post_mentions_bot_via_props() -> None:
    uid = "u1"
    post = {"message": "hi", "props": {"mentions": {"mentions": {uid: True}}}}
    assert mattermost_post_mentions_bot(post, uid) is True


def test_mattermost_post_mentions_bot_props_mentions_json_string() -> None:
    uid = "u1"
    post = {"message": "hi", "props": {"mentions": json.dumps([uid])}}
    assert mattermost_post_mentions_bot(post, uid) is True


def test_mattermost_broadcast_mentions_bot_json_string() -> None:
    uid = "botx"
    assert mattermost_broadcast_mentions_bot({"mentions": json.dumps([uid, "other"])}, uid) is True
    assert mattermost_broadcast_mentions_bot({"mentions": json.dumps(["other"])}, uid) is False


def test_mattermost_posted_event_open_channel_at_username_only() -> None:
    uid = "botuserid"
    post_obj = {
        "id": "post1",
        "channel_id": "ch1",
        "user_id": "human",
        "message": "@kashiwaas what is 2+2?",
        "root_id": "",
        "props": {},
    }
    data = {"channel_type": "O", "post": json.dumps(post_obj)}
    ev = mattermost_posted_event_from_broadcast(data, bot_user_id=uid, bot_username="kashiwaas")
    assert ev is not None
    assert ev.raw_text == "@kashiwaas what is 2+2?"


def test_mattermost_posted_event_from_broadcast_string_post() -> None:
    uid = "botx"
    post_obj = {
        "id": "post1",
        "channel_id": "ch1",
        "user_id": "human",
        "message": f"@{uid} explain tuples",
        "root_id": "",
        "props": {"mentions": {"mentions": {uid: True}}},
    }
    data = {"post": json.dumps(post_obj)}
    ev = mattermost_posted_event_from_broadcast(data, bot_user_id=uid)
    assert ev is not None
    assert ev.channel_id == "ch1"
    assert ev.root_post_id == "post1"
    assert ev.event_post_id == "post1"
    assert "tuples" in ev.raw_text


def test_mattermost_posted_event_direct_message_without_at_mention() -> None:
    """DM posts often omit @userid in the body; treat as addressed to the bot."""
    uid = "botx"
    post_obj = {
        "id": "post1",
        "channel_id": "ch1",
        "user_id": "human",
        "message": "こんばんは",
        "root_id": "",
        "props": {},
    }
    data = {"channel_type": "D", "post": json.dumps(post_obj)}
    ev = mattermost_posted_event_from_broadcast(data, bot_user_id=uid)
    assert ev is not None
    assert ev.raw_text == "こんばんは"


def test_mattermost_posted_event_from_broadcast_top_level_mentions_string() -> None:
    uid = "botx"
    post_obj = {
        "id": "post1",
        "channel_id": "ch1",
        "user_id": "human",
        "message": "hello without at-token",
        "root_id": "",
        "props": {},
    }
    data = {"mentions": json.dumps([uid]), "post": json.dumps(post_obj)}
    ev = mattermost_posted_event_from_broadcast(data, bot_user_id=uid)
    assert ev is not None
    assert ev.channel_id == "ch1"
    assert ev.event_post_id == "post1"


def test_mattermost_posted_event_skips_self() -> None:
    uid = "botx"
    post_obj = {
        "id": "post1",
        "channel_id": "ch1",
        "user_id": uid,
        "message": "hello",
        "root_id": "",
    }
    assert mattermost_posted_event_from_broadcast({"post": post_obj}, bot_user_id=uid) is None


@patch("src.bot.kashiwaas_mattermost._is_duplicate_event", return_value=False)
@patch("src.bot.kashiwaas_mattermost.threading.Thread")
def test_handle_mattermost_mention_runs_cursor(mock_thread_class, _mock_dup) -> None:
    def run_target_immediately(*args, **kwargs):
        target = kwargs.get("target")
        mock_thread = MagicMock()

        def start():
            if target:
                target()

        mock_thread.start.side_effect = start
        return mock_thread

    mock_thread_class.side_effect = run_target_immediately

    ev = MattermostPostedEvent(
        channel_id="ch1",
        root_post_id="root1",
        event_post_id="evt1",
        raw_text="@botuid What is Python?",
    )
    mm = MagicMock()
    cursor = MagicMock()
    cursor.ask.return_value = AgentResult(
        agent_id="a1",
        status=AgentStatus.FINISHED,
        messages=[AgentMessage(id="m1", type="assistant_message", text="Python is a language.")],
    )
    cursor.get_latest_assistant_message_obj.side_effect = lambda msgs: msgs[-1] if msgs else None
    store = MagicMock()
    store.get.return_value = None

    mm_bot.handle_mattermost_mention(
        ev=ev,
        mm=mm,
        cursor_client=cursor,
        thread_store=store,
        bot_user_id="botuid",
    )

    mm.add_reaction.assert_called()
    cursor.ask.assert_called_once()
    store.set.assert_called()


@patch("src.bot.kashiwaas_mattermost._is_duplicate_event", return_value=False)
def test_handle_mattermost_mention_help_only_no_cursor(_mock_dup) -> None:
    ev = MattermostPostedEvent(
        channel_id="ch1",
        root_post_id="root1",
        event_post_id="evt1",
        raw_text="@botuid help!",
    )
    mm = MagicMock()
    cursor = MagicMock()
    store = MagicMock()

    mm_bot.handle_mattermost_mention(
        ev=ev,
        mm=mm,
        cursor_client=cursor,
        thread_store=store,
        bot_user_id="botuid",
    )

    cursor.ask.assert_not_called()
    mm.create_post.assert_called_once()
    assert "Example" in mm.create_post.call_args[0][1]
