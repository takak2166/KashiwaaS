#!/usr/bin/env bash
# Phase 1 E2E: v1 create + follow-up on self-hosted machine (TAK-136).
# Requires: curl, jq, CURSOR_API_KEY, CURSOR_ENV_NAME (and optional CURSOR_ENV_TYPE).
set -euo pipefail

: "${CURSOR_API_KEY:?Set CURSOR_API_KEY}"
ENV_TYPE="${CURSOR_ENV_TYPE:-machine}"
: "${CURSOR_ENV_NAME:?Set CURSOR_ENV_NAME}"

API="https://api.cursor.com"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
POLL_TIMEOUT="${POLL_TIMEOUT:-600}"

require_jq_field() {
  local json="$1" expr="$2" label="$3"
  local val
  val=$(echo "$json" | jq -r "$expr // empty")
  if [[ -z "$val" ]]; then
    echo "FAIL: missing $label in response: $json" >&2
    exit 1
  fi
  echo "$val"
}

normalize_result() {
  echo "$1" | tr -d '\n\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

poll_run() {
  local agent_id="$1" run_id="$2"
  local elapsed=0 status
  while (( elapsed < POLL_TIMEOUT )); do
    status=$(curl -sf -u "$CURSOR_API_KEY:" "$API/v1/agents/$agent_id/runs/$run_id" | jq -r '.status')
    case "$status" in
      FINISHED|ERROR|CANCELLED|EXPIRED) echo "$status"; return 0 ;;
    esac
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
  done
  echo "TIMEOUT" >&2
  return 1
}

echo "== Phase 1: POST /v1/agents (env_only) =="
CREATE=$(curl -sf -u "$CURSOR_API_KEY:" -H 'Content-Type: application/json' \
  "$API/v1/agents" \
  -d "{\"prompt\":{\"text\":\"Reply with exactly: E2E_OK\"},\"env\":{\"type\":\"$ENV_TYPE\",\"name\":\"$CURSOR_ENV_NAME\"},\"autoCreatePR\":false}")
AGENT_ID=$(require_jq_field "$CREATE" '.agent.id' 'agent.id')
RUN_ID=$(require_jq_field "$CREATE" '.run.id' 'run.id')
echo "agent=$AGENT_ID run=$RUN_ID"

STATUS=$(poll_run "$AGENT_ID" "$RUN_ID")
RESULT=$(curl -sf -u "$CURSOR_API_KEY:" "$API/v1/agents/$AGENT_ID/runs/$RUN_ID" | jq -r '.result // empty')
NORM=$(normalize_result "$RESULT")
echo "create status=$STATUS result=${NORM:0:80}"

if [[ "$STATUS" != "FINISHED" || "$NORM" != "E2E_OK" ]]; then
  echo "FAIL: create did not finish with result E2E_OK (got: ${NORM:-<empty>})" >&2
  exit 1
fi

echo "== Phase 1: POST /v1/agents/{id}/runs (follow-up) =="
FUP=$(curl -sf -u "$CURSOR_API_KEY:" -H 'Content-Type: application/json' \
  -d '{"prompt":{"text":"Reply with exactly: E2E_FOLLOWUP_OK"}}' \
  "$API/v1/agents/$AGENT_ID/runs")
RUN2=$(require_jq_field "$FUP" '.run.id' 'run.id')
echo "follow-up run=$RUN2 (agent unchanged: $AGENT_ID)"

STATUS2=$(poll_run "$AGENT_ID" "$RUN2")
RESULT2=$(curl -sf -u "$CURSOR_API_KEY:" "$API/v1/agents/$AGENT_ID/runs/$RUN2" | jq -r '.result // empty')
NORM2=$(normalize_result "$RESULT2")
echo "follow-up status=$STATUS2 result=${NORM2:0:80}"

if [[ "$STATUS2" != "FINISHED" || "$NORM2" != "E2E_FOLLOWUP_OK" ]]; then
  echo "FAIL: follow-up did not finish with result E2E_FOLLOWUP_OK (got: ${NORM2:-<empty>})" >&2
  exit 1
fi

echo "PASS: Phase 1 curl E2E complete"
