"""Construct ``CursorClient`` from loaded ``AppConfig``."""

from src.cursor.client import CursorClient
from src.utils.config import AppConfig


def build_cursor_client(cfg: AppConfig) -> CursorClient:
    return CursorClient(
        api_key=cfg.cursor.api_key,
        source_repository=cfg.cursor.source_repository,
        source_ref=cfg.cursor.source_ref,
        poll_interval=cfg.cursor.poll_interval,
        poll_timeout=cfg.cursor.poll_timeout,
        model=cfg.cursor.model,
        conversation_retry_max_retries=cfg.cursor.conversation_retry_max_retries,
        conversation_retry_delay_seconds=cfg.cursor.conversation_retry_delay_seconds,
        conversation_text_stabilize_interval_seconds=cfg.cursor.conversation_text_stabilize_interval_seconds,
        conversation_text_stabilize_required_matches=cfg.cursor.conversation_text_stabilize_required_matches,
        conversation_text_stabilize_max_rounds=cfg.cursor.conversation_text_stabilize_max_rounds,
    )
