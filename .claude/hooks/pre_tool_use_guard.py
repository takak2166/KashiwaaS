#!/usr/bin/env python3
"""preToolUse hook: deny dangerous shell commands and edits to secret paths. Prints JSON to stdout."""  # noqa: E501

from __future__ import annotations

import json
import re
import sys
from typing import Any

DENY_SHELL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)git\s+push\s+--force"), "git push --force is blocked"),
    (re.compile(r"(?i)git\s+push\s+-f\b"), "git push -f is blocked"),
    (re.compile(r"(?i)\brm\s+(-rf\b|-fr\b)"), "rm -rf / rm -fr is blocked"),  # noqa: E501
    (re.compile(r"(?i)--no-verify\b"), "--no-verify is blocked"),
    (re.compile(r"(?i)git\s+reset\s+--hard"), "git reset --hard is blocked"),
    (re.compile(r"(?i):\s*\(\s*\)\s*\{\s*:\s*\|:\s*&\s*\}\s*;"), "fork bomb / destructive shell is blocked"),  # noqa: E501
]


def _iter_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_iter_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_iter_strings(item))
    return out


def _shell_command(payload: dict[str, Any]) -> str:
    ti = payload.get("tool_input") or {}
    if isinstance(ti, dict):
        cmd = ti.get("command")
        if isinstance(cmd, str):
            return cmd
    return ""


def _deny_secret_path(path: str) -> str | None:
    p = path.replace("\\", "/").strip()
    if not p:
        return None
    lowered = p.lower()
    if "/.github/secrets" in lowered or lowered.endswith("/.github/secrets"):
        return "edits under .github/secrets are blocked"
    if ".github/secrets" in lowered:
        return "edits under .github/secrets are blocked"
    base = p.rsplit("/", 1)[-1].lower()
    if base == ".env" or (base.startswith(".env.") and base != ".env.example"):
        return "editing .env files is blocked (use .env.example or user env)"
    if lowered.endswith("id_rsa") or lowered.endswith(".pem"):
        return "editing key material paths is blocked"
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"permission": "allow"}))
        return

    tool = str(payload.get("tool_name") or "")

    # Cursor uses "Shell"; Claude Code uses "Bash" for shell invocations.
    if tool in ("Shell", "Bash"):
        cmd = _shell_command(payload)
        for pat, msg in DENY_SHELL_PATTERNS:
            if pat.search(cmd):
                print(
                    json.dumps(
                        {
                            "permission": "deny",
                            "user_message": msg,
                            "agent_message": msg + " — use a safer alternative.",  # noqa: E501
                        }
                    )
                )
                return
        print(json.dumps({"permission": "allow"}))
        return

    # "Edit" is Claude Code; others match Cursor tool names.
    if tool in ("Write", "Edit", "StrReplace", "Delete", "NotebookEdit"):
        ti = payload.get("tool_input")
        for s in _iter_strings(ti):
            if len(s) > 4096:
                continue
            reason = _deny_secret_path(s)
            if reason:
                print(
                    json.dumps(
                        {
                            "permission": "deny",
                            "user_message": reason,
                            "agent_message": reason,
                        }
                    )
                )
                return
        print(json.dumps({"permission": "allow"}))
        return

    print(json.dumps({"permission": "allow"}))


if __name__ == "__main__":
    main()
