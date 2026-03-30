"""Smoke tests for .claude/hooks/pre_tool_use_guard.py (stdin JSON → stdout JSON)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_GUARD = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "pre_tool_use_guard.py"


def _run(payload: dict[str, object]) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(_GUARD)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


@pytest.mark.parametrize(
    ("tool_name", "cmd"),
    [
        ("Shell", "git push --force"),
        ("Bash", "git push --force"),
        ("Bash", "rm -rf /tmp/x"),
    ],
)
def test_shell_and_bash_deny_dangerous_commands(tool_name: str, cmd: str) -> None:
    out = _run({"tool_name": tool_name, "tool_input": {"command": cmd}})
    assert out["permission"] == "deny"


def test_bash_allows_safe_command() -> None:
    out = _run({"tool_name": "Bash", "tool_input": {"command": "make test"}})
    assert out["permission"] == "allow"


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("Write", {"path": ".env", "contents": "x"}),
        ("Edit", {"path": ".env", "contents": "x"}),
    ],
)
def test_write_and_edit_deny_secret_files(tool_name: str, tool_input: dict[str, str]) -> None:
    out = _run({"tool_name": tool_name, "tool_input": tool_input})
    assert out["permission"] == "deny"


def test_edit_allows_safe_path() -> None:
    out = _run(
        {
            "tool_name": "Edit",
            "tool_input": {"path": "src/foo.py", "contents": "x"},
        }
    )
    assert out["permission"] == "allow"
