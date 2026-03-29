"""
Cursor Cloud Agents API Client
Provides functionality for interacting with Cursor's Cloud Agents API for Q&A.
"""

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


class AgentStatus(str, Enum):
    CREATING = "CREATING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


TERMINAL_STATUSES = {AgentStatus.FINISHED, AgentStatus.STOPPED, AgentStatus.ERROR}


@dataclass
class AgentMessage:
    id: str
    type: str
    text: str


@dataclass
class AgentResult:
    agent_id: str
    status: AgentStatus
    messages: List[AgentMessage]


class CursorAPIError(Exception):
    """Raised when Cursor API returns an error response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Cursor API error ({status_code}): {message}")


class CursorTimeoutError(Exception):
    """Raised when polling for agent completion exceeds the timeout."""


class CursorClient:
    """
    Client for Cursor Cloud Agents API.

    Uses the Cloud Agents API to send prompts and retrieve AI responses.
    Each Q&A session creates a cloud agent tied to a repository.
    """

    def __init__(
        self,
        api_key: str,
        source_repository: str,
        source_ref: str = "main",
        poll_interval: int = 5,
        poll_timeout: int = DEFAULT_CURSOR_POLL_TIMEOUT_SECONDS,
        model: Optional[str] = None,
        conversation_retry_max_retries: int = 4,
        conversation_retry_delay_seconds: float = 1.5,
    ):
        self.api_key = api_key
        self.source_repository = source_repository
        self.source_ref = source_ref
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        # Optional model name for Cloud Agents API (e.g., "composer-2")
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
        """
        Return the list of model IDs recommended for the launch endpoint.

        Use these values for CURSOR_MODEL. The list does not include "default";
        omit model or use "default"/"Auto" for API default.
        """
        data = self._request("GET", "/v0/models")
        return list(data.get("models", []))

    def create_agent(self, prompt: str) -> str:
        """
        Launch a new cloud agent with the given prompt.

        Returns:
            The agent ID.
        """
        payload: Dict[str, Any] = {
            "prompt": {"text": prompt},
            "source": {
                "repository": self.source_repository,
                "ref": self.source_ref,
            },
            "target": {
                "autoCreatePr": False,
            },
        }
        # model: optional. Use "default" or omit for API default; explicit ID (e.g. composer-2) otherwise.
        # Treat empty, "default", or "Auto" (case-insensitive) as "use API default".
        if self.model:
            normalized = self.model.strip().lower()
            if normalized not in ("", "default", "auto"):
                payload["model"] = self.model.strip()
            # else: omit payload["model"] so API uses user/team/system default
        data = self._request("POST", "/v0/agents", json=payload)
        agent_id = data["id"]
        logger.info(f"Created agent {agent_id} for prompt: {prompt[:80]}...")
        return agent_id

    def get_agent_status(self, agent_id: str) -> AgentStatus:
        """Get the current status of an agent."""
        data = self._request("GET", f"/v0/agents/{agent_id}")
        raw_status = data.get("status", "ERROR")
        try:
            return AgentStatus(raw_status)
        except ValueError:
            logger.warning(f"Unknown agent status: {raw_status}")
            return AgentStatus.ERROR

    def get_conversation(self, agent_id: str) -> List[AgentMessage]:
        """Retrieve the conversation history of an agent."""
        data = self._request("GET", f"/v0/agents/{agent_id}/conversation")
        messages = []
        for msg in data.get("messages", []):
            messages.append(
                AgentMessage(
                    id=msg.get("id", ""),
                    type=msg.get("type", ""),
                    text=msg.get("text", ""),
                )
            )
        return messages

    def get_conversation_after_complete(
        self,
        agent_id: str,
        expected_previous_message_id: Optional[str] = None,
        max_retries: Optional[int] = None,
        delay_seconds: Optional[float] = None,
    ) -> List[AgentMessage]:
        """
        Retrieve the conversation after agent completion, with retries.

        When expected_previous_message_id is set (e.g. from the last reply in
        this thread), retries until the latest assistant message id differs from
        it, so we avoid returning a stale snapshot that still shows the previous
        answer (API eventual consistency). Uses exponential backoff between
        retries (delay_seconds * 2^attempt). Uses conversation_retry_max_retries
        and conversation_retry_delay_seconds from the client when not overridden.
        """
        max_retries = max_retries if max_retries is not None else self.conversation_retry_max_retries
        delay_seconds = delay_seconds if delay_seconds is not None else self.conversation_retry_delay_seconds
        if max_retries < 1:
            return self.get_conversation(agent_id)
        for attempt in range(max_retries):
            messages = self.get_conversation(agent_id)
            latest = self.get_latest_assistant_message_obj(messages)
            if expected_previous_message_id is None or latest is None:
                return messages
            if latest.id != expected_previous_message_id:
                return messages
            if attempt < max_retries - 1:
                time.sleep(delay_seconds * (2**attempt))
        return messages

    def send_followup(self, agent_id: str, prompt: str) -> None:
        """Send a follow-up prompt to an existing agent."""
        payload = {"prompt": {"text": prompt}}
        self._request("POST", f"/v0/agents/{agent_id}/followup", json=payload)
        logger.info(f"Sent followup to agent {agent_id}: {prompt[:80]}...")

    def poll_until_complete(
        self,
        agent_id: str,
        *,
        on_poll: Optional[Callable[[float], None]] = None,
    ) -> AgentStatus:
        """
        Poll the agent status until it reaches a terminal state or times out.

        Args:
            agent_id: Cloud agent id.
            on_poll: Called after each non-terminal poll wait with cumulative elapsed
                seconds (after ``poll_interval`` sleeps). Omitted or ``None`` skips.

        Returns:
            The final AgentStatus.

        Raises:
            CursorTimeoutError: If polling exceeds the timeout.
        """
        elapsed = 0.0
        while elapsed < self.poll_timeout:
            status = self.get_agent_status(agent_id)
            if status in TERMINAL_STATUSES:
                logger.info(f"Agent {agent_id} reached terminal status: {status.value}")
                return status
            time.sleep(self.poll_interval)
            elapsed += float(self.poll_interval)
            if on_poll is not None:
                on_poll(elapsed)

        raise CursorTimeoutError(f"Agent {agent_id} did not complete within {self.poll_timeout}s")

    def ask(
        self,
        prompt: str,
        expected_previous_message_id: Optional[str] = None,
        on_poll: Optional[Callable[[float], None]] = None,
    ) -> AgentResult:
        """
        Create an agent, wait for completion, and return the conversation.
        """
        agent_id = self.create_agent(prompt)
        status = self.poll_until_complete(agent_id, on_poll=on_poll)
        if status == AgentStatus.FINISHED:
            messages = self.get_conversation_after_complete(
                agent_id, expected_previous_message_id=expected_previous_message_id
            )
        else:
            # Avoid pointless retry delays for ERROR/STOPPED agents
            messages = self.get_conversation(agent_id)
        return AgentResult(agent_id=agent_id, status=status, messages=messages)

    def followup(
        self,
        agent_id: str,
        prompt: str,
        expected_previous_message_id: Optional[str] = None,
        on_poll: Optional[Callable[[float], None]] = None,
    ) -> AgentResult:
        """
        Send a follow-up to an existing agent and return updated conversation.
        """
        self.send_followup(agent_id, prompt)
        status = self.poll_until_complete(agent_id, on_poll=on_poll)
        if status == AgentStatus.FINISHED:
            messages = self.get_conversation_after_complete(
                agent_id, expected_previous_message_id=expected_previous_message_id
            )
        else:
            # Avoid pointless retry delays for ERROR/STOPPED agents
            messages = self.get_conversation(agent_id)
        return AgentResult(agent_id=agent_id, status=status, messages=messages)

    def get_latest_assistant_message_obj(self, messages: List[AgentMessage]) -> Optional[AgentMessage]:
        """
        Return the most recent assistant message (full message with id and text).

        Cursor API returns messages in chronological order (oldest first).
        So the last assistant_message in the list is the latest.
        """
        latest: Optional[AgentMessage] = None
        for msg in messages:
            if msg.type == "assistant_message":
                latest = msg
        return latest

    def get_latest_assistant_message(self, messages: List[AgentMessage]) -> Optional[str]:
        """
        Extract the most recent assistant message from a conversation.

        Cursor API returns messages in chronological order (oldest first).
        So the last assistant_message in the list is the latest.
        """
        msg = self.get_latest_assistant_message_obj(messages)
        return msg.text if msg else None
