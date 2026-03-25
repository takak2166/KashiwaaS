#!/usr/bin/env bash
# Cursor afterFileEdit: run project lint (see Makefile). Exit 2 on failure blocks the edit flow.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HOOK_DIR/lib.sh"

[[ -n "${POETRY_CACHE_DIR:-}" ]] && export POETRY_CACHE_DIR
[[ -n "${POETRY_VIRTUALENVS_PATH:-}" ]] && export POETRY_VIRTUALENVS_PATH

PROJECT_ROOT="$(project_root)"
cd "$PROJECT_ROOT"

# Hook protocol: consume JSON payload from stdin
cat >/dev/null

if PY="$(resolve_python ruff)"; then
  log=$(mktemp)
  if ! "$PY" -m ruff format . >"$log" 2>&1; then
    cat "$log" >&2
    rm -f "$log"
    echo "after-file-edit-lint: ruff format failed" >&2
    exit 2
  fi
  if ! "$PY" -m ruff check . --fix >>"$log" 2>&1; then
    cat "$log" >&2
    rm -f "$log"
    echo "after-file-edit-lint: ruff check failed" >&2
    exit 2
  fi
  emit_ruff_ok_json "$log" "$PY"
  rm -f "$log"
  exit 0
fi

if ! command -v make >/dev/null 2>&1; then
  echo "after-file-edit-lint: make not found in PATH" >&2
  exit 2
fi

log=$(mktemp)
if ! make lint >"$log" 2>&1; then
  cat "$log" >&2
  rm -f "$log"
  echo "after-file-edit-lint: make lint failed" >&2
  echo "after-file-edit-lint: hint: run \`poetry install\` or use a project-local .venv (poetry config virtualenvs.in-project true)." >&2
  exit 2
fi
PY_JSON="$(resolve_python ruff || true)"
emit_ruff_ok_json "$log" "${PY_JSON:-python3}"
rm -f "$log"
exit 0
