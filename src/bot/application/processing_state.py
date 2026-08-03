"""Logical processing outcome for chat reactions (platform emoji mapping lives in adapters)."""

from __future__ import annotations

from enum import StrEnum


class ProcessingState(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
