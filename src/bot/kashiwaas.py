"""
KashiwaaS Bot Module
Slack Socket Mode application that answers questions via Cursor Cloud Agents API.
"""

import os
import re
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.bot.thread_store import ThreadStore
from src.cursor.client import (
    AgentStatus,
    CursorAPIError,
    CursorClient,
    CursorTimeoutError,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

SLACK_MESSAGE_MAX_LENGTH = 4000
MENTION_PATTERN = re.compile(r"<@[\w]+>")

thread_store = ThreadStore()


def create_app() -> App:
    """Create and configure the Slack Bolt application."""
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    cursor_client = CursorClient(
        api_key=os.environ["CURSOR_API_KEY"],
        source_repository=os.environ.get(
            "CURSOR_SOURCE_REPOSITORY",
            "https://github.com/takak2166/KashiwaaS",
        ),
        source_ref=os.environ.get("CURSOR_SOURCE_REF", "main"),
        poll_interval=int(os.environ.get("CURSOR_POLL_INTERVAL", "5")),
        poll_timeout=int(os.environ.get("CURSOR_POLL_TIMEOUT", "300")),
        model=os.environ.get("CURSOR_MODEL", "composer-1.5"),
    )

    @app.event("app_mention")
    def handle_mention(event, say, client):
        _handle_mention(event, say, client, cursor_client)

    return app


def _extract_question(text: str) -> str:
    """Remove mention tags and extract the actual question text."""
    question = MENTION_PATTERN.sub("", text).strip()
    return question


def _split_message(text: str, max_length: int = SLACK_MESSAGE_MAX_LENGTH) -> list[str]:
    """Split a long message into chunks respecting Slack's character limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind(" ", 0, max_length)
        if split_pos <= 0:
            split_pos = max_length

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n ")

    return chunks


def _add_reaction(client, channel: str, timestamp: str, name: str) -> None:
    try:
        client.reactions_add(channel=channel, timestamp=timestamp, name=name)
    except Exception as e:
        logger.warning(f"Failed to add reaction '{name}': {e}")


def _remove_reaction(client, channel: str, timestamp: str, name: str) -> None:
    try:
        client.reactions_remove(channel=channel, timestamp=timestamp, name=name)
    except Exception as e:
        logger.warning(f"Failed to remove reaction '{name}': {e}")


def _handle_mention(event, say, client, cursor_client: CursorClient):
    """Process an app_mention event."""
    text = event.get("text", "")
    channel = event.get("channel", "")
    event_ts = event.get("ts", "")
    thread_ts = event.get("thread_ts") or event_ts

    logger.info(f"app_mention received: channel={channel}, ts={event_ts}, thread_ts={thread_ts}, text={text!r}")

    question = _extract_question(text)
    if not question:
        say(text="質問を入力してください。例: `@kashiwaas Pythonのasyncの使い方は？`", thread_ts=thread_ts)
        return

    _add_reaction(client, channel, event_ts, "eyes")

    def _process():
        try:
            agent_id = thread_store.get(thread_ts)

            if agent_id:
                logger.info(f"Followup in thread {thread_ts} -> agent {agent_id}")
                result = cursor_client.followup(agent_id, question)
            else:
                logger.info(f"New question in thread {thread_ts}: {question[:80]}...")
                result = cursor_client.ask(question)
                thread_store.set(thread_ts, result.agent_id)

            if result.status == AgentStatus.ERROR:
                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "x")
                say(
                    text="申し訳ありません、回答の生成中にエラーが発生しました。しばらくしてからお試しください。",
                    thread_ts=thread_ts,
                )
                return

            answer = cursor_client.get_latest_assistant_message(result.messages)
            if not answer:
                _remove_reaction(client, channel, event_ts, "eyes")
                _add_reaction(client, channel, event_ts, "x")
                say(text="回答を取得できませんでした。もう一度お試しください。", thread_ts=thread_ts)
                return

            chunks = _split_message(answer)
            for chunk in chunks:
                say(text=chunk, thread_ts=thread_ts)

            _remove_reaction(client, channel, event_ts, "eyes")
            _add_reaction(client, channel, event_ts, "white_check_mark")

        except CursorTimeoutError:
            _remove_reaction(client, channel, event_ts, "eyes")
            _add_reaction(client, channel, event_ts, "x")
            say(
                text="回答の生成がタイムアウトしました。質問を短くするか、もう一度お試しください。",
                thread_ts=thread_ts,
            )
        except CursorAPIError as e:
            logger.error(f"Cursor API error: {e}")
            _remove_reaction(client, channel, event_ts, "eyes")
            _add_reaction(client, channel, event_ts, "x")
            if e.status_code in (401, 403):
                say(text="Cursor API の認証設定に問題があります。管理者に確認してください。", thread_ts=thread_ts)
            else:
                say(
                    text="申し訳ありません、回答の取得に失敗しました。しばらくしてからお試しください。",
                    thread_ts=thread_ts,
                )
        except Exception as e:
            logger.error(f"Unexpected error handling mention: {e}")
            _remove_reaction(client, channel, event_ts, "eyes")
            _add_reaction(client, channel, event_ts, "x")
            say(
                text="予期しないエラーが発生しました。しばらくしてからお試しください。",
                thread_ts=thread_ts,
            )

    threading.Thread(target=_process, daemon=True).start()


def main():
    """Entry point for the kashiwaas bot."""
    app = create_app()
    handler = SocketModeHandler(
        app=app,
        app_token=os.environ["SLACK_APP_TOKEN"],
    )
    logger.info("KashiwaaS bot starting...")
    handler.start()


if __name__ == "__main__":
    main()
