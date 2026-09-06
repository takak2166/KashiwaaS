"""
Cursor Cloud Agents API v1 Client

Launches agents on cloud, pool, or machine environments and polls run status.
"""

from __future__ import annotations

import time
from base64 import b64encode
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import requests

from src.utils.config import DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS
from src.utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.cursor.com"


class RunStatus(str, Enum):
    CREATING = "CREATING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# Backward-compatible alias for bot layer imports
AgentStatus = RunStatus

TERMINAL_STATUSES = {
    RunStatus.FINISHED,
    RunStatus.ERROR,
    RunStatus.CANCELLED,
    RunStatus.EXPIRED,
}

FAILURE_STATUSES = {RunStatus.ERROR, RunStatus.CANCELLED, RunStatus.EXPIRED}


@dataclass
class AgentResult:
    agent_id: str
    run_id: str
    status: RunStatus
    result_text: Optional[str] = None


class CursorAPIError(Exception):
    """Raised when Cursor API returns an error response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Cursor API error ({status_code}): {message}")


class CursorTimeoutError(Exception):
    """Raised when polling for run completion exceeds the timeout."""


class CursorClient:
    """
    Client for Cursor Cloud Agents API v1.

    Creates agents (with initial run) and follow-up runs; polls until terminal
    and reads assistant text from the run ``result`` field.
    """

    def __init__(
        self,
        api_key: str,
        *,
        env_type: Optional[str] = None,
        env_name: Optional[str] = None,
        launch_mode: str = "repo",
        source_repository: str = "https://github.com/takak2166/KashiwaaS",
        source_ref: str = "main",
        auto_create_pr: bool = False,
        poll_interval: int = 5,
        poll_timeout: int = DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS,
        model: Optional[str] = None,
        conversation_retry_max_retries: int = 4,
        conversation_retry_delay_seconds: float = 1.5,
    ):
        self.api_key = api_key
        self.env_type = env_type
        self.env_name = env_name
        self.launch_mode = launch_mode
        self.source_repository = source_repository
        self.source_ref = source_ref
        self.auto_create_pr = auto_create_pr
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.model = model
        self.conversation_retry_max_retries = conversation_retry_max_retries
        self.conversation_retry_delay_seconds = conversation_retry_delay_seconds

        encoded = b64encode(f"{api_key}:".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"{BASE_URL}{path}"
        timeout = kwargs.pop("timeout", 60)
        response = requests.request(method, url, headers=self.headers, timeout=timeout, **kwargs)

        if response.status_code == 429:
            raise CursorAPIError(429, "Rate limit exceeded")
        if response.status_code == 401:
            raise CursorAPIError(401, "Invalid API key")
        if response.status_code == 403:
            raise CursorAPIError(403, "Insufficient permissions")
        if not response.ok:
            raise CursorAPIError(response.status_code, response.text)

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def list_models(self) -> List[str]:
        """Return model IDs from GET /v1/models."""
        data = self._request("GET", "/v1/models")
        items = data.get("items") or data.get("models") or []
        if items and isinstance(items[0], dict):
            return [str(item.get("id", "")) for item in items if item.get("id")]
        return list(items)

    def _model_payload(self) -> Optional[Dict[str, Any]]:
        if not self.model:
            return None
        normalized = self.model.strip().lower()
        if normalized in ("", "default", "auto"):
            return None
        return {"id": self.model.strip()}

    def _env_payload(self) -> Optional[Dict[str, str]]:
        if not self.env_type:
            return None
        env: Dict[str, str] = {"type": self.env_type}
        if self.env_name:
            env["name"] = self.env_name
        return env

    def _repos_payload(self) -> Optional[List[Dict[str, str]]]:
        if self.launch_mode != "repo":
            return None
        return [
            {
                "url": self.source_repository,
                "startingRef": self.source_ref,
            }
        ]

    def _build_create_payload(self, prompt: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "prompt": {"text": prompt},
            "autoCreatePR": self.auto_create_pr,
        }
        model = self._model_payload()
        if model is not None:
            payload["model"] = model
        env = self._env_payload()
        if env is not None:
            payload["env"] = env
        repos = self._repos_payload()
        if repos is not None:
            payload["repos"] = repos
        return payload

    def create_agent(self, prompt: str) -> tuple[str, str]:
        """
        POST /v1/agents — create agent and enqueue initial run.

        Returns:
            (agent_id, run_id)
        """
        data = self._request("POST", "/v1/agents", json=self._build_create_payload(prompt))
        agent_id = data["agent"]["id"]
        run_id = data["run"]["id"]
        logger.info("Created agent {} run {} for prompt: {}...", agent_id, run_id, prompt[:80])
        return agent_id, run_id

    def send_followup(self, agent_id: str, prompt: str) -> str:
        """POST /v1/agents/{id}/runs — enqueue a follow-up run."""
        payload = {"prompt": {"text": prompt}}
        data = self._request("POST", f"/v1/agents/{agent_id}/runs", json=payload)
        run_id = data["run"]["id"]
        logger.info("Sent followup run {} to agent {}: {}...", run_id, agent_id, prompt[:80])
        return run_id

    def get_run_status(self, agent_id: str, run_id: str) -> RunStatus:
        """GET /v1/agents/{id}/runs/{runId} — run status only."""
        data = self._request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")
        raw_status = data.get("status", "ERROR")
        try:
            return RunStatus(raw_status)
        except ValueError:
            logger.warning("Unknown run status: {}", raw_status)
            return RunStatus.ERROR

    def get_run(self, agent_id: str, run_id: str) -> Dict[str, Any]:
        """GET /v1/agents/{id}/runs/{runId} — full run record."""
        return self._request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")

    def poll_until_complete(
        self,
        agent_id: str,
        run_id: str,
        *,
        on_poll: Optional[Callable[[float], None]] = None,
    ) -> RunStatus:
        """
        Poll run status until terminal or timeout.

        Raises:
            CursorTimeoutError: If polling exceeds ``poll_timeout``.
        """
        elapsed = 0.0
        while elapsed < self.poll_timeout:
            status = self.get_run_status(agent_id, run_id)
            if status in TERMINAL_STATUSES:
                logger.info("Run {} on agent {} reached terminal status: {}", run_id, agent_id, status.value)
                return status
            time.sleep(self.poll_interval)
            elapsed += float(self.poll_interval)
            if on_poll is not None:
                on_poll(elapsed)

        raise CursorTimeoutError(f"Run {run_id} on agent {agent_id} did not complete within {self.poll_timeout}s")

    def _result_from_run(self, agent_id: str, run_id: str, status: RunStatus) -> AgentResult:
        result_text: Optional[str] = None
        if status == RunStatus.FINISHED:
            data = self.get_run(agent_id, run_id)
            raw = data.get("result")
            if isinstance(raw, str) and raw:
                result_text = raw
        return AgentResult(
            agent_id=agent_id,
            run_id=run_id,
            status=status,
            result_text=result_text,
        )

    def get_run_after_complete(
        self,
        agent_id: str,
        run_id: str,
        *,
        expected_previous_run_id: Optional[str] = None,
        max_retries: Optional[int] = None,
        delay_seconds: Optional[float] = None,
    ) -> AgentResult:
        """
        Re-fetch a terminal run, retrying when the run id still matches a stale
        previous id (eventual consistency on duplicate detection path).
        """
        max_retries = max_retries if max_retries is not None else self.conversation_retry_max_retries
        delay_seconds = delay_seconds if delay_seconds is not None else self.conversation_retry_delay_seconds
        if max_retries < 1:
            data = self.get_run(agent_id, run_id)
            status = RunStatus(data.get("status", "ERROR"))
            return self._result_from_run(agent_id, run_id, status)

        for attempt in range(max_retries):
            data = self.get_run(agent_id, run_id)
            status = RunStatus(data.get("status", "ERROR"))
            current_run_id = data.get("id", run_id)
            if expected_previous_run_id is None or current_run_id != expected_previous_run_id:
                return self._result_from_run(agent_id, current_run_id, status)
            if attempt < max_retries - 1:
                time.sleep(delay_seconds * (2**attempt))

        data = self.get_run(agent_id, run_id)
        status = RunStatus(data.get("status", "ERROR"))
        return self._result_from_run(agent_id, data.get("id", run_id), status)

    def ask(
        self,
        prompt: str,
        expected_previous_run_id: Optional[str] = None,
        on_poll: Optional[Callable[[float], None]] = None,
    ) -> AgentResult:
        """Create agent + initial run, poll, return result."""
        agent_id, run_id = self.create_agent(prompt)
        status = self.poll_until_complete(agent_id, run_id, on_poll=on_poll)
        if status == RunStatus.FINISHED and expected_previous_run_id is not None:
            return self.get_run_after_complete(
                agent_id,
                run_id,
                expected_previous_run_id=expected_previous_run_id,
            )
        return self._result_from_run(agent_id, run_id, status)

    def followup(
        self,
        agent_id: str,
        prompt: str,
        expected_previous_run_id: Optional[str] = None,
        on_poll: Optional[Callable[[float], None]] = None,
    ) -> AgentResult:
        """Send follow-up run, poll, return result."""
        run_id = self.send_followup(agent_id, prompt)
        status = self.poll_until_complete(agent_id, run_id, on_poll=on_poll)
        if status == RunStatus.FINISHED and expected_previous_run_id is not None:
            return self.get_run_after_complete(
                agent_id,
                run_id,
                expected_previous_run_id=expected_previous_run_id,
            )
        return self._result_from_run(agent_id, run_id, status)
