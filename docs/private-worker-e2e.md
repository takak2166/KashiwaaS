# Private Worker E2E verification (TAK-136)

Validate self-hosted **machine** launches before enabling the Slack Bot path in production.

**Platform:** Slack only (Mattermost out of scope).

**Target worker:** see [private-worker.md](private-worker.md) — resolve `CURSOR_ENV_NAME` via curl; set `CURSOR_ENV_TYPE=machine` and `CURSOR_LAUNCH_MODE=env_only` in host `.env` for the Bot.

## Phases

| Phase | Goal | Blocker if fail |
|-------|------|-----------------|
| 0 | `.env` has `CURSOR_ENV_*`, worker connected | Do not start Bot |
| 1 | curl: new agent + follow-up on ubuntu24 machine | Do not start Bot |
| 2 | Bot + Valkey running (Compose or systemd) | Do not run Slack tests |
| 3 | Slack: new thread mention | — |
| 4 | Slack: same-thread follow-up (agent id unchanged) | — |
| 5 | Triage failures by layer (API / Worker / Bot / Valkey / Slack) | — |

## Phase 0 — prerequisites

```bash
test -n "$CURSOR_API_KEY"
curl -sf -u "$CURSOR_API_KEY:" "https://api.cursor.com/v1/me" >/dev/null
curl -sf -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v0/private-workers?status=all&limit=50" | jq -e '.workers | length > 0'
```

Resolve and export `CURSOR_ENV_NAME` (see [private-worker.md](private-worker.md)).

## Phase 1 — curl (required before Bot)

Use the helper script (mock-free, hits live API):

```bash
export CURSOR_API_KEY=...   # user key from host .env
export CURSOR_ENV_TYPE=machine
export CURSOR_ENV_NAME=<your-machine-env-name>

./scripts/cursor_v1_e2e.sh
```

Manual equivalent:

```bash
# Create (env_only — no repos)
CREATE=$(curl -sf -u "$CURSOR_API_KEY:" -H 'Content-Type: application/json' \
  -d '{"prompt":{"text":"Reply with exactly: E2E_OK"},"env":{"type":"machine","name":"'"$CURSOR_ENV_NAME"'"},"autoCreatePR":false}' \
  https://api.cursor.com/v1/agents)
AGENT_ID=$(echo "$CREATE" | jq -r '.agent.id // empty')
RUN_ID=$(echo "$CREATE" | jq -r '.run.id // empty')
test -n "$AGENT_ID" && test -n "$RUN_ID"

# Poll until terminal
until STATUS=$(curl -sf -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v1/agents/$AGENT_ID/runs/$RUN_ID" | jq -r '.status')
  [[ "$STATUS" == "FINISHED" || "$STATUS" == "ERROR" || "$STATUS" == "CANCELLED" || "$STATUS" == "EXPIRED" ]]
do sleep 5; done

curl -sf -u "$CURSOR_API_KEY:" "https://api.cursor.com/v1/agents/$AGENT_ID/runs/$RUN_ID" | jq .

# Follow-up (same agent)
FUP=$(curl -sf -u "$CURSOR_API_KEY:" -H 'Content-Type: application/json' \
  -d '{"prompt":{"text":"Reply with exactly: E2E_FOLLOWUP_OK"}}' \
  "https://api.cursor.com/v1/agents/$AGENT_ID/runs")
RUN2=$(echo "$FUP" | jq -r '.run.id // empty')
test -n "$RUN2"
# Poll RUN2 similarly; agent id must stay $AGENT_ID
```

**Pass:** Phase 1 create + follow-up both reach `FINISHED` with `result` exactly `E2E_OK` and `E2E_FOLLOWUP_OK` (after trimming whitespace).

## Phase 2 — Bot startup

Start Valkey and the Bot before Slack tests. Set `CURSOR_LAUNCH_MODE=env_only` (and other `CURSOR_*` vars) in host `.env` — the curl script does not read launch mode.

1. Valkey up (`docker compose up -d valkey` or `kashiwaas-valkey.service`).
2. Bot up (see [bot.md](bot.md) / systemd unit).

## Phase 3–4 — Slack

1. `@kashiwaas` new message → assistant reply in thread.
2. Reply in same thread → follow-up (check logs: `Followup`, same `agent_id` in Valkey).

## Failure triage

| Symptom | Layer | Action |
|---------|-------|--------|
| 401 / 403 on curl | API key | [cursor-secrets.md](cursor-secrets.md) 403 triage |
| 404 / worker not found | Worker name | Verify `CURSOR_ENV_NAME` vs [private-worker.md](private-worker.md) |
| Run stuck `RUNNING` | Worker | Reconnect Cursor Remote; see TAK-133 health check |
| curl OK, Slack silent | Bot / Slack | Socket Mode tokens, channel invite, Bot logs |
| Follow-up creates new agent | Valkey | `VALKEY_URL` reachable; one Bot replica |

## Related

- [private-worker.md](private-worker.md)
