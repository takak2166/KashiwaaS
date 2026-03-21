"""Tests for Markdown to Slack mrkdwn conversion."""

from src.bot.slack_mrkdwn import markdown_to_slack_mrkdwn


def test_bold_and_emphasis():
    out = markdown_to_slack_mrkdwn("**a** and *b*")
    assert "*a*" in out
    assert "_b_" in out


def test_unordered_list():
    out = markdown_to_slack_mrkdwn("- one\n- two")
    assert "- one" in out
    assert "- two" in out


def test_ordered_list():
    out = markdown_to_slack_mrkdwn("1. a\n2. b")
    assert "1. a" in out
    assert "2. b" in out


def test_link():
    out = markdown_to_slack_mrkdwn("[label](https://example.com)")
    assert "<https://example.com|label>" == out


def test_strikethrough():
    out = markdown_to_slack_mrkdwn("~~x~~")
    assert "~x~" in out


def test_fallback_on_empty():
    assert markdown_to_slack_mrkdwn("") == ""
