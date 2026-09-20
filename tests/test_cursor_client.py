"""
Tests for Cursor Cloud Agents API v1 client
"""

from unittest.mock import MagicMock, patch

import pytest

from src.cursor.client import (
    CursorAPIError,
    CursorClient,
    CursorTimeoutError,
    RunStatus,
)


@pytest.fixture
def cursor_client():
    return CursorClient(
        api_key="test_key",
        env_type="machine",
        env_name="cursor-agent-worker-test",
        launch_mode="env_only",
        source_repository="https://github.com/test/repo",
        source_ref="main",
        poll_interval=0.01,
        poll_timeout=0.05,
    )


class TestCursorClient:
    @patch("src.cursor.client.requests.request")
    def test_create_agent_env_only(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"agent":{"id":"bc_abc123"},"run":{"id":"run_001"}}'
        mock_response.json.return_value = {
            "agent": {"id": "bc_abc123"},
            "run": {"id": "run_001"},
        }
        mock_request.return_value = mock_response

        agent_id, run_id = cursor_client.create_agent("What is Python?")

        assert agent_id == "bc_abc123"
        assert run_id == "run_001"
        call_kwargs = mock_request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "/v1/agents" in call_kwargs[0][1]
        payload = call_kwargs[1]["json"]
        assert payload["prompt"]["text"] == "What is Python?"
        assert payload["env"] == {"type": "machine", "name": "cursor-agent-worker-test"}
        assert "repos" not in payload
        assert payload["autoCreatePR"] is False

    @patch("src.cursor.client.requests.request")
    def test_create_agent_machine_repo_mode(self, mock_request):
        client = CursorClient(
            api_key="k",
            env_type="machine",
            env_name="cursor-agent-worker-test",
            launch_mode="repo",
            source_repository="https://github.com/t/r",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"agent":{"id":"x"},"run":{"id":"r1"}}'
        mock_response.json.return_value = {"agent": {"id": "x"}, "run": {"id": "r1"}}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert payload["env"] == {"type": "machine", "name": "cursor-agent-worker-test"}
        assert payload["repos"] == [{"url": "https://github.com/t/r", "startingRef": "main"}]

    @patch("src.cursor.client.requests.request")
    def test_create_agent_repo_mode(self, mock_request):
        client = CursorClient(
            api_key="k",
            launch_mode="repo",
            source_repository="https://github.com/t/r",
            source_ref="main",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"agent":{"id":"x"},"run":{"id":"r1"}}'
        mock_response.json.return_value = {"agent": {"id": "x"}, "run": {"id": "r1"}}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert payload["repos"] == [{"url": "https://github.com/t/r", "startingRef": "main"}]
        assert "env" not in payload

    @patch("src.cursor.client.requests.request")
    def test_create_agent_model_auto_omits_model(self, mock_request):
        client = CursorClient(
            api_key="k",
            launch_mode="env_only",
            model="Auto",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"agent":{"id":"x"},"run":{"id":"r1"}}'
        mock_response.json.return_value = {"agent": {"id": "x"}, "run": {"id": "r1"}}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert "model" not in payload

    @patch("src.cursor.client.requests.request")
    def test_create_agent_model_explicit(self, mock_request):
        client = CursorClient(
            api_key="k",
            launch_mode="env_only",
            model="composer-2",
        )
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"agent":{"id":"x"},"run":{"id":"r1"}}'
        mock_response.json.return_value = {"agent": {"id": "x"}, "run": {"id": "r1"}}
        mock_request.return_value = mock_response

        client.create_agent("q")
        payload = mock_request.call_args[1]["json"]
        assert payload["model"] == {"id": "composer-2"}

    @patch("src.cursor.client.requests.request")
    def test_list_models(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"items":[{"id":"composer-2"}]}'
        mock_response.json.return_value = {"items": [{"id": "composer-2"}]}
        mock_request.return_value = mock_response

        models = cursor_client.list_models()

        assert models == ["composer-2"]
        assert "/v1/models" in mock_request.call_args[0][1]

    @patch("src.cursor.client.requests.request")
    def test_get_run_status(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"status":"FINISHED","result":"done"}'
        mock_response.json.return_value = {"id": "run_001", "status": "FINISHED", "result": "done"}
        mock_request.return_value = mock_response

        status = cursor_client.get_run_status("bc_abc123", "run_001")

        assert status == RunStatus.FINISHED

    @patch("src.cursor.client.requests.request")
    def test_send_followup(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"run":{"id":"run_002"}}'
        mock_response.json.return_value = {"run": {"id": "run_002"}}
        mock_request.return_value = mock_response

        run_id = cursor_client.send_followup("bc_abc123", "Tell me more")

        assert run_id == "run_002"
        call_kwargs = mock_request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "/v1/agents/bc_abc123/runs" in call_kwargs[0][1]

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
        mock_response.content = b'{"status":"FINISHED"}'
        mock_response.json.return_value = {"id": "run_001", "status": "FINISHED"}
        mock_request.return_value = mock_response

        status = cursor_client.poll_until_complete("bc_abc123", "run_001")

        assert status == RunStatus.FINISHED

    @patch("src.cursor.client.requests.request")
    def test_poll_until_complete_timeout(self, mock_request, cursor_client):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"status":"RUNNING"}'
        mock_response.json.return_value = {"id": "run_001", "status": "RUNNING"}
        mock_request.return_value = mock_response

        with pytest.raises(CursorTimeoutError):
            cursor_client.poll_until_complete("bc_abc123", "run_001")

    @patch("src.cursor.client.time.sleep")
    @patch("src.cursor.client.requests.request")
    def test_poll_until_complete_calls_on_poll(self, mock_request, mock_sleep):
        running = MagicMock()
        running.ok = True
        running.status_code = 200
        running.content = b'{"status":"RUNNING"}'
        running.json.return_value = {"id": "run_x", "status": "RUNNING"}
        finished = MagicMock()
        finished.ok = True
        finished.status_code = 200
        finished.content = b'{"status":"FINISHED"}'
        finished.json.return_value = {"id": "run_x", "status": "FINISHED"}
        mock_request.side_effect = [running, running, finished]

        client = CursorClient(
            api_key="k",
            launch_mode="env_only",
            poll_interval=1,
            poll_timeout=30,
        )
        seen: list[float] = []

        def on_poll(elapsed: float) -> None:
            seen.append(elapsed)

        status = client.poll_until_complete("bc_x", "run_x", on_poll=on_poll)
        assert status == RunStatus.FINISHED
        assert seen == [1.0, 2.0]

    @patch("src.cursor.client.requests.request")
    def test_ask_full_flow(self, mock_request, cursor_client):
        create_resp = self._make_response(
            200,
            {"agent": {"id": "bc_abc123"}, "run": {"id": "run_001"}},
        )
        status_resp = self._make_response(200, {"id": "run_001", "status": "FINISHED"})
        result_resp = self._make_response(
            200,
            {"id": "run_001", "status": "FINISHED", "result": "A language."},
        )
        mock_request.side_effect = [create_resp, status_resp, result_resp]

        result = cursor_client.ask("What is Python?")

        assert result.agent_id == "bc_abc123"
        assert result.run_id == "run_001"
        assert result.status == RunStatus.FINISHED
        assert result.result_text == "A language."

    @patch("src.cursor.client.requests.request")
    def test_followup_full_flow(self, mock_request, cursor_client):
        followup_resp = self._make_response(200, {"run": {"id": "run_002"}})
        status_resp = self._make_response(200, {"id": "run_002", "status": "FINISHED"})
        result_resp = self._make_response(
            200,
            {"id": "run_002", "status": "FINISHED", "result": "More details."},
        )
        mock_request.side_effect = [followup_resp, status_resp, result_resp]

        result = cursor_client.followup("bc_abc123", "Tell me more")

        assert result.agent_id == "bc_abc123"
        assert result.run_id == "run_002"
        assert result.result_text == "More details."

    @patch("src.cursor.client.requests.request")
    def test_followup_error_skips_result_fetch(self, mock_request, cursor_client):
        followup_resp = self._make_response(200, {"run": {"id": "run_002"}})
        status_resp = self._make_response(200, {"id": "run_002", "status": "ERROR"})
        mock_request.side_effect = [followup_resp, status_resp]

        result = cursor_client.followup("bc_abc123", "Tell me more")

        assert result.status == RunStatus.ERROR
        assert result.result_text is None

    @patch("src.cursor.client.time.sleep")
    @patch("src.cursor.client.requests.request")
    def test_get_run_after_complete_retries_when_run_id_unchanged(self, mock_request, mock_sleep, cursor_client):
        stale = self._make_response(200, {"id": "old_id", "status": "FINISHED", "result": "old"})
        fresh = self._make_response(200, {"id": "new_id", "status": "FINISHED", "result": "new"})
        mock_request.side_effect = [stale, fresh, fresh]

        result = cursor_client.get_run_after_complete(
            "agent_1",
            "run_1",
            expected_previous_run_id="old_id",
            max_retries=3,
            delay_seconds=0.01,
        )
        assert result.run_id == "new_id"
        assert result.result_text == "new"

    def test_basic_auth_header(self, cursor_client):
        assert cursor_client.headers["Authorization"].startswith("Basic ")

    @staticmethod
    def _make_response(status_code, json_data):
        resp = MagicMock()
        resp.ok = 200 <= status_code < 300
        resp.status_code = status_code
        resp.content = b"data"
        resp.json.return_value = json_data
        return resp
