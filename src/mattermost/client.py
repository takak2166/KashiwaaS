"""
Thin Mattermost REST helpers (posts, reactions) using mattermostdriver.
"""

from __future__ import annotations

from typing import Any


class MattermostBotClient:
    """Small wrapper around ``Driver`` for bot posting and reactions."""

    def __init__(self, driver: Any):
        self._driver = driver

    def create_post(self, channel_id: str, message: str, root_id: str = "") -> dict:
        opts: dict[str, str] = {"channel_id": channel_id, "message": message}
        if root_id:
            opts["root_id"] = root_id
        return self._driver.posts.create_post(opts)

    def add_reaction(self, user_id: str, post_id: str, emoji_name: str) -> None:
        self._driver.reactions.create_reaction({"user_id": user_id, "post_id": post_id, "emoji_name": emoji_name})

    def remove_reaction(self, user_id: str, post_id: str, emoji_name: str) -> None:
        self._driver.reactions.delete_reaction(user_id, post_id, emoji_name)
