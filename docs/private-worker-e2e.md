# Private Worker E2E verification (TAK-136)

Validate self-hosted **machine** launches before enabling the Slack Bot path in production.

**Platform:** Slack only (Mattermost out of scope).

**Target worker:** see [private-worker.md](private-worker.md) — `CURSOR_ENV_TYPE=machine`, `CURSOR_ENV_NAME=cursor-agent-worker-676f7f7b4d`, `CURSOR_LAUNCH_MODE=env_only`.

## Phases

| Phase | Goal | Blocker if fail |
|-------|------|-----------------|
| 0 | `.env` has `CURSOR_ENV_*`, worker connected | Do not start Bot |
| 1 | curl: new agent + follow-up on ubuntu24 machine | Do not start Bot |
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

## Phase 1 — curl (required before Bot)

Use the helper script (mock-free, hits live API):

```bash
export CURSOR_API_KEY=...   # user key from host .env
export CURSOR_ENV_TYPE=machine
export CURSOR_ENV_NAME=cursor-agent-worker-676f7f7b4d
export CURSOR_LAUNCH_MODE=env_only

./scripts/cursor_v1_e2e.sh
```

Manual equivalent:

```bash
# Create (env_only — no repos)
CREATE=$(curl -sf -u "$CURSOR_API_KEY:" -H 'Content-Type: application/json' \
  -d '{"prompt":{"text":"Reply with exactly: E2E_OK"},"env":{"type":"machine","name":"'"$CURSOR_ENV_NAME"'"},"autoCreatePR":false}' \
  https://api.cursor.com/v1/agents)
AGENT_ID=$(echo "$CREATE" | jq -r '.agent.id')
RUN_ID=$(echo "$CREATE" | jq -r '.run.id')

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
RUN2=$(echo "$FUP" | jq -r '.run.id')
# Poll RUN2 similarly; agent id must stay $AGENT_ID
```

**Pass:** Phase 1 create + follow-up both reach `FINISHED` with non-empty `result`.

## Phase 3–4 — Slack

1. Start Bot (see [bot.md](bot.md) / systemd unit).
2. `@kashiwaas` new message → assistant reply in thread.
3. Reply in same thread → follow-up (check logs: `Followup`, same `agent_id` in Valkey).

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
- [production-cutover-runbook.md](production-cutover-runbook.md)
