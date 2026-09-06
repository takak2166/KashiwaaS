"""Construct ``CursorClient`` from loaded ``AppConfig``."""

from src.cursor.client import CursorClient
from src.utils.config import AppConfig


def build_cursor_client(cfg: AppConfig) -> CursorClient:
    return CursorClient(
        api_key=cfg.cursor.api_key or "",
        env_type=cfg.cursor.env_type,
        env_name=cfg.cursor.env_name,
        launch_mode=cfg.cursor.launch_mode,
        source_repository=cfg.cursor.source_repository,
        source_ref=cfg.cursor.source_ref,
        auto_create_pr=cfg.cursor.auto_create_pr,
        poll_interval=cfg.cursor.poll_interval,
        poll_timeout=cfg.cursor.poll_timeout,
        model=cfg.cursor.model,
        conversation_retry_max_retries=cfg.cursor.conversation_retry_max_retries,
        conversation_retry_delay_seconds=cfg.cursor.conversation_retry_delay_seconds,
    )
