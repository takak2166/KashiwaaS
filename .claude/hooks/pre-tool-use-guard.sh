#!/usr/bin/env bash
# Cursor preToolUse: block dangerous tools / secret paths (see pre_tool_use_guard.py).
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HOOK_DIR/pre_tool_use_guard.py"
