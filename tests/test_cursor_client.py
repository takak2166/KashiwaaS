"""
Tests for Cursor Cloud Agents API client
"""

from unittest.mock import MagicMock, patch

import pytest

from src.cursor.client import (
    AgentMessage,
    AgentStatus,
    CursorAPIError,
    CursorClient,
    CursorTimeoutError,
)


@pytest.fixture
def cursor_client():
    return CursorClient(
        api_key="test_key",
        source_repository="https://github.com/test/repo",
        source_ref="main",
        poll_interval=0.01,
        poll_timeout=0.05,
    )


class TestCursorClient:
    """Tests for CursorClient class"""

    @patch("src.cursor.client.requests.request")
    def test_create_agent(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"id": "bc_abc123"}'
        mock_response.json.return_value = {
            "id": "bc_abc123",
            "status": "CREATING",
        }
        mock_request.return_value = mock_response

        agent_id = cursor_client.create_agent("What is Python?")

        assert agent_id == "bc_abc123"
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "/v0/agents" in call_kwargs[0][1]
        payload = call_kwargs[1]["json"]
        assert payload["prompt"]["text"] == "What is Python?"
        assert payload["source"]["repository"] == "https://github.com/test/repo"
        assert payload["target"]["autoCreatePr"] is False
        assert "model" not in payload

    @patch("src.cursor.client.requests.request")
    def test_create_agent_model_auto_omits_model(self, mock_request):
        client = CursorClient(
            api_key="k",
            source_repository="https://github.com/t/r",
            model="Auto",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"id": "x"}'
        mock_response.json.return_value = {"id": "x"}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert "model" not in payload

    @patch("src.cursor.client.requests.request")
    def test_create_agent_model_default_omits_model(self, mock_request):
        client = CursorClient(
            api_key="k",
            source_repository="https://github.com/t/r",
            model="default",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"id": "x"}'
        mock_response.json.return_value = {"id": "x"}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert "model" not in payload

    @patch("src.cursor.client.requests.request")
    def test_create_agent_model_explicit_sends_model(self, mock_request):
        client = CursorClient(
            api_key="k",
            source_repository="https://github.com/t/r",
            model="gpt-5.2",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"id": "x"}'
        mock_response.json.return_value = {"id": "x"}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert payload["model"] == "gpt-5.2"

    @patch("src.cursor.client.requests.request")
    def test_list_models(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"models": ["gpt-5.2", "claude-4-sonnet-thinking"]}'
        mock_response.json.return_value = {
            "models": ["gpt-5.2", "claude-4-sonnet-thinking"],
        }
        mock_request.return_value = mock_response

        models = cursor_client.list_models()

        assert models == ["gpt-5.2", "claude-4-sonnet-thinking"]
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "GET"
        assert "/v0/models" in call_args[0][1]

    @patch("src.cursor.client.requests.request")
    def test_get_agent_status(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"status": "FINISHED"}'
        mock_response.json.return_value = {"id": "bc_abc123", "status": "FINISHED"}
        mock_request.return_value = mock_response

        status = cursor_client.get_agent_status("bc_abc123")

        assert status == AgentStatus.FINISHED

    @patch("src.cursor.client.requests.request")
    def test_get_agent_status_unknown(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"status": "UNKNOWN_STATUS"}'
        mock_response.json.return_value = {"id": "bc_abc123", "status": "UNKNOWN_STATUS"}
        mock_request.return_value = mock_response

        status = cursor_client.get_agent_status("bc_abc123")

        assert status == AgentStatus.ERROR

    @patch("src.cursor.client.requests.request")
    def test_get_conversation(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b"{}"
        mock_response.json.return_value = {
            "id": "bc_abc123",
            "messages": [
                {"id": "msg_001", "type": "user_message", "text": "What is Python?"},
                {"id": "msg_002", "type": "assistant_message", "text": "Python is a programming language."},
            ],
        }
        mock_request.return_value = mock_response

        messages = cursor_client.get_conversation("bc_abc123")

        assert len(messages) == 2
        assert messages[0].type == "user_message"
        assert messages[1].type == "assistant_message"
        assert messages[1].text == "Python is a programming language."

    @patch("src.cursor.client.requests.request")
    def test_send_followup(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"id": "bc_abc123"}'
        mock_response.json.return_value = {"id": "bc_abc123"}
        mock_request.return_value = mock_response

        cursor_client.send_followup("bc_abc123", "Tell me more")

        call_kwargs = mock_request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "/v0/agents/bc_abc123/followup" in call_kwargs[0][1]
        assert call_kwargs[1]["json"]["prompt"]["text"] == "Tell me more"

    @patch("src.cursor.client.requests.request")
    def test_delete_agent(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"id": "bc_abc123"}'
        mock_response.json.return_value = {"id": "bc_abc123"}
        mock_request.return_value = mock_response

        cursor_client.delete_agent("bc_abc123")

        call_kwargs = mock_request.call_args
        assert call_kwargs[0][0] == "DELETE"
        assert "/v0/agents/bc_abc123" in call_kwargs[0][1]

    @patch("src.cursor.client.requests.request")
    def test_delete_agent_handles_error(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_request.return_value = mock_response

        cursor_client.delete_agent("bc_nonexistent")

    @patch("src.cursor.client.requests.request")
    def test_api_error_429(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit"
        mock_request.return_value = mock_response

        with pytest.raises(CursorAPIError) as exc_info:
            cursor_client.get_agent_status("bc_abc123")
        assert exc_info.value.status_code == 429

    @patch("src.cursor.client.requests.request")
    def test_api_error_401(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_request.return_value = mock_response

        with pytest.raises(CursorAPIError) as exc_info:
            cursor_client.create_agent("test")
        assert exc_info.value.status_code == 401

    @patch("src.cursor.client.requests.request")
    def test_poll_until_complete_finished(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b"{}"
        mock_response.json.return_value = {"id": "bc_abc123", "status": "FINISHED"}
        mock_request.return_value = mock_response

        status = cursor_client.poll_until_complete("bc_abc123")

        assert status == AgentStatus.FINISHED

    @patch("src.cursor.client.requests.request")
    def test_poll_until_complete_timeout(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b"{}"
        mock_response.json.return_value = {"id": "bc_abc123", "status": "RUNNING"}
        mock_request.return_value = mock_response

        with pytest.raises(CursorTimeoutError):
            cursor_client.poll_until_complete("bc_abc123")

    def test_get_latest_assistant_message(self, cursor_client):
        # API returns chronological (oldest first): latest assistant is last in list
        messages = [
            AgentMessage(id="1", type="user_message", text="question"),
            AgentMessage(id="2", type="assistant_message", text="first answer"),
            AgentMessage(id="3", type="user_message", text="followup"),
            AgentMessage(id="4", type="assistant_message", text="second answer"),
        ]

        result = cursor_client.get_latest_assistant_message(messages)
        assert result == "second answer"

    def test_get_latest_assistant_message_none(self, cursor_client):
        messages = [
            AgentMessage(id="1", type="user_message", text="question"),
        ]

        result = cursor_client.get_latest_assistant_message(messages)
        assert result is None

    def test_get_latest_assistant_message_empty(self, cursor_client):
        result = cursor_client.get_latest_assistant_message([])
        assert result is None

    @patch("src.cursor.client.time.sleep")
    def test_get_conversation_after_complete_retries_when_latest_id_unchanged(self, mock_sleep, cursor_client):
        """When expected_previous_message_id equals latest message id, retry until it changes."""
        stale = [
            AgentMessage(id="1", type="user_message", text="q"),
            AgentMessage(id="old_id", type="assistant_message", text="old answer"),
        ]
        fresh = [
            AgentMessage(id="1", type="user_message", text="q"),
            AgentMessage(id="new_id", type="assistant_message", text="new answer"),
        ]
        with patch.object(cursor_client, "get_conversation", side_effect=[stale, fresh]):
            result = cursor_client.get_conversation_after_complete(
                "agent_1",
                expected_previous_message_id="old_id",
                max_retries=3,
                delay_seconds=0.01,
            )
        assert len(result) == 2
        assert result[1].id == "new_id" and result[1].text == "new answer"
        mock_sleep.assert_called_once()

    @patch("src.cursor.client.time.sleep")
    def test_get_conversation_after_complete_no_retry_when_id_differs(self, mock_sleep, cursor_client):
        """When latest message id differs from expected_previous_message_id, return immediately."""
        messages = [
            AgentMessage(id="1", type="user_message", text="q"),
            AgentMessage(id="new_id", type="assistant_message", text="answer"),
        ]
        with patch.object(cursor_client, "get_conversation", return_value=messages):
            result = cursor_client.get_conversation_after_complete(
                "agent_1", expected_previous_message_id="old_id", max_retries=3
            )
        assert len(result) == 2
        assert result[1].id == "new_id"
        mock_sleep.assert_not_called()

    def test_get_conversation_after_complete_max_retries_zero(self, cursor_client):
        """When max_retries is 0, return get_conversation result without UnboundLocalError."""
        messages = [
            AgentMessage(id="1", type="user_message", text="q"),
            AgentMessage(id="2", type="assistant_message", text="a"),
        ]
        with patch.object(cursor_client, "get_conversation", return_value=messages):
            result = cursor_client.get_conversation_after_complete(
                "agent_1", max_retries=0
            )
        assert result == messages

    def test_get_latest_assistant_message_message(self, cursor_client):
        # Chronological order: last assistant is latest
        messages = [
            AgentMessage(id="2", type="assistant_message", text="first"),
            AgentMessage(id="4", type="assistant_message", text="second"),
        ]
        msg = cursor_client.get_latest_assistant_message_message(messages)
        assert msg is not None
        assert msg.id == "4" and msg.text == "second"

    def test_basic_auth_header(self, cursor_client):
        assert "Authorization" in cursor_client.headers
        assert cursor_client.headers["Authorization"].startswith("Basic ")

    @patch("src.cursor.client.requests.request")
    def test_ask_full_flow(self, mock_request, cursor_client):
        """Test the full ask flow: create -> poll -> get conversation"""
        conv_resp = self._make_response(
            200,
            {
                "id": "bc_abc123",
                "messages": [
                    {"id": "msg_001", "type": "user_message", "text": "What is Python?"},
                    {"id": "msg_002", "type": "assistant_message", "text": "A language."},
                ],
            },
        )
        responses = [
            self._make_response(200, {"id": "bc_abc123", "status": "CREATING"}),
            self._make_response(200, {"id": "bc_abc123", "status": "FINISHED"}),
            conv_resp,
        ]
        mock_request.side_effect = responses

        result = cursor_client.ask("What is Python?")

        assert result.agent_id == "bc_abc123"
        assert result.status == AgentStatus.FINISHED
        assert len(result.messages) == 2

    @patch("src.cursor.client.requests.request")
    def test_followup_full_flow(self, mock_request, cursor_client):
        """Test the full followup flow: followup -> poll -> get conversation"""
        conv_resp = self._make_response(
            200,
            {
                "id": "bc_abc123",
                "messages": [
                    {"id": "msg_001", "type": "user_message", "text": "What is Python?"},
                    {"id": "msg_002", "type": "assistant_message", "text": "A language."},
                    {"id": "msg_003", "type": "user_message", "text": "Tell me more"},
                    {"id": "msg_004", "type": "assistant_message", "text": "More details."},
                ],
            },
        )
        responses = [
            self._make_response(200, {"id": "bc_abc123"}),
            self._make_response(200, {"id": "bc_abc123", "status": "FINISHED"}),
            conv_resp,
        ]
        mock_request.side_effect = responses

        result = cursor_client.followup("bc_abc123", "Tell me more")

        assert result.agent_id == "bc_abc123"
        assert result.status == AgentStatus.FINISHED
        assert len(result.messages) == 4

    @staticmethod
    def _make_response(status_code, json_data):
        resp = MagicMock()
        resp.ok = 200 <= status_code < 300
        resp.status_code = status_code
        resp.content = b"data"
        resp.json.return_value = json_data
        return resp
