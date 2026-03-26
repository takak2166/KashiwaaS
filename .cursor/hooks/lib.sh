# Shared helpers for Cursor hooks. Poetry may pick a different venv when the hook runs with a stripped
# environment; we try several POETRY_CACHE_DIR values and pick a Python that can run pytest/ruff.

_LIB_SH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

project_root() {
  echo "${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}}"
}

# Lines suitable for: while IFS= read -r line; do ... done
_poetry_cache_candidates() {
  if [[ -n "${POETRY_CACHE_DIR:-}" ]]; then
    printf '%s\n' "$POETRY_CACHE_DIR"
  fi
  printf '%s\n' "$HOME/.cache/pypoetry"
  local d
  for d in /tmp/cursor-*/poetry /tmp/cursor-sandbox-cache/*/poetry; do
    [[ -d "$d" ]] && printf '%s\n' "$d"
  done
}

# Resolve venv root path (absolute). Prefer --full-path; avoid `env info -p` when POETRY_CACHE_DIR is empty.
_poetry_venv_root() {
  local out
  out=$(poetry env list --full-path 2>/dev/null | head -n1 | awk '{print $1}')
  if [[ -n "$out" && "$out" == /* ]]; then
    echo "$out"
    return 0
  fi
  return 1
}

# Args: mode "pytest" | "ruff"
_python_ok() {
  local py="$1"
  local mode="$2"
  case "$mode" in
    pytest)
      "$py" -c "import slack_bolt" 2>/dev/null && "$py" -m pytest --version >/dev/null 2>&1
      ;;
    ruff)
      "$py" -m ruff --version >/dev/null 2>&1
      ;;
    *)
      return 1
      ;;
  esac
}

# Print one python path to stdout, or nothing.
resolve_python() {
  local mode="$1"
  local root py p pr
  root="$(project_root)"
  cd "$root" || return 1

  if [[ -x "$root/.venv/bin/python" ]] && _python_ok "$root/.venv/bin/python" "$mode"; then
    echo "$root/.venv/bin/python"
    return 0
  fi

  local cache
  while IFS= read -r cache || [[ -n "$cache" ]]; do
    [[ -z "$cache" ]] && continue
    if [[ ! -d "$cache" ]]; then
      continue
    fi
    export POETRY_CACHE_DIR="$cache"
    if p="$(_poetry_venv_root)" && [[ -x "$p/bin/python" ]] && _python_ok "$p/bin/python" "$mode"; then
      echo "$p/bin/python"
      return 0
    fi
  done < <(_poetry_cache_candidates)

  unset POETRY_CACHE_DIR 2>/dev/null || true
  if command -v poetry >/dev/null 2>&1; then
    pr=$(cd "$root" && poetry run which python 2>/dev/null || true)
    if [[ -n "$pr" && "$pr" == /* && -x "$pr" ]] && _python_ok "$pr" "$mode"; then
      echo "$pr"
      return 0
    fi
  fi

  return 1
}

# Run a command with all output captured. On success: no stdout/stderr (Cursor may treat stderr as errors).
# On failure: print captured output to stderr and return 1.
run_silent_or_fail() {
  local log
  log=$(mktemp)
  if ! "$@" >"$log" 2>&1; then
    cat "$log" >&2
    rm -f "$log"
    return 1
  fi
  rm -f "$log"
  return 0
}

# Print one JSON line to stdout from a pytest log file (success path only). Args: log_path python_path
emit_pytest_ok_json() {
  local log="$1"
  local py="${2:-python3}"
  if ! "$py" "$_LIB_SH_DIR/emit_pytest_ok_json.py" "$log"; then
    printf '%s\n' '{"event":"stop","status":"ok"}'
  fi
}

# Print one JSON line from combined ruff format + check log. Args: log_path python_path
emit_ruff_ok_json() {
  local log="$1"
  local py="${2:-python3}"
  if ! "$py" "$_LIB_SH_DIR/emit_ruff_ok_json.py" "$log"; then
    printf '%s\n' '{"event":"afterFileEdit","status":"ok"}'
  fi
}
