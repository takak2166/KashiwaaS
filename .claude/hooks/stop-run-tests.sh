#!/usr/bin/env bash
# Cursor stop: run full test suite. Exit 2 on failure blocks completion (see Cursor hooks docs).
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HOOK_DIR/lib.sh"

# Do not export empty POETRY_* — Poetry treats unset vs empty differently.
[[ -n "${POETRY_CACHE_DIR:-}" ]] && export POETRY_CACHE_DIR
[[ -n "${POETRY_VIRTUALENVS_PATH:-}" ]] && export POETRY_VIRTUALENVS_PATH

PROJECT_ROOT="$(project_root)"
cd "$PROJECT_ROOT"

# Hook protocol: consume JSON payload from stdin
cat >/dev/null

if PY="$(resolve_python pytest)"; then
  log=$(mktemp)
  if ! "$PY" -m pytest >"$log" 2>&1; then
    cat "$log" >&2
    rm -f "$log"
    echo "stop-run-tests: pytest failed — fix tests before the run can finish." >&2
    exit 2
  fi
  emit_pytest_ok_json "$log" "$PY"
  rm -f "$log"
  exit 0
fi

if ! command -v make >/dev/null 2>&1; then
  echo "stop-run-tests: make not found in PATH" >&2
  exit 2
fi

log=$(mktemp)
if ! make test >"$log" 2>&1; then
  cat "$log" >&2
  rm -f "$log"
  echo "stop-run-tests: make test failed — fix tests before the run can finish." >&2
  echo "stop-run-tests: hint: run \`poetry install\` or \`poetry config virtualenvs.in-project true\` and reinstall so .venv is used." >&2
  exit 2
fi
PY_JSON="$(resolve_python pytest || true)"
emit_pytest_ok_json "$log" "${PY_JSON:-python3}"
rm -f "$log"
exit 0
