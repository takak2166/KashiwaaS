"""
Shared Block Kit markdown helpers (KashiwaaS bot, SlackClient reports).

https://docs.slack.dev/reference/block-kit/blocks/markdown-block/
"""

from typing import Any, Callable, Dict, List

SLACK_MESSAGE_MAX_LENGTH = 4000
SLACK_MARKDOWN_BLOCK_TEXT_MAX = 12000


def split_slack_message_text(text: str, max_length: int = SLACK_MESSAGE_MAX_LENGTH) -> List[str]:
    """Split long text at newlines/spaces for Slack message or markdown-block limits."""
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    rest = text
    while rest:
        if len(rest) <= max_length:
            chunks.append(rest)
            break

        split_pos = rest.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = rest.rfind(" ", 0, max_length)
        if split_pos <= 0:
            split_pos = max_length

        chunks.append(rest[:split_pos])
        rest = rest[split_pos:]
        if rest.startswith("\n"):
            rest = rest[1:]
        elif rest.startswith(" "):
            rest = rest[1:]

    return chunks


def fallback_notification_text(text: str, max_len: int = SLACK_MESSAGE_MAX_LENGTH) -> str:
    """Plain `text` for chat.postMessage (notifications, search); keep under Slack limits."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def markdown_blocks_for_text(text: str, max_chunk: int = SLACK_MARKDOWN_BLOCK_TEXT_MAX) -> List[Dict[str, Any]]:
    """Block Kit `markdown` blocks for full body (single post, multiple blocks if needed)."""
    chunks = split_slack_message_text(text, max_chunk)
    return [{"type": "markdown", "text": chunk} for chunk in chunks]


def say_markdown_chunks(say: Callable[..., None], chunks: List[str], thread_ts: str) -> None:
    """One chat.postMessage per chunk (Bolt `say` in a thread)."""
    for chunk in chunks:
        say(
            text=fallback_notification_text(chunk),
            blocks=[{"type": "markdown", "text": chunk}],
            thread_ts=thread_ts,
        )


def say_markdown_text(say: Callable[..., None], text: str, thread_ts: str) -> None:
    """Split long assistant text then post with :func:`say_markdown_chunks`."""
    chunks = split_slack_message_text(text, SLACK_MARKDOWN_BLOCK_TEXT_MAX)
    say_markdown_chunks(say, chunks, thread_ts)
