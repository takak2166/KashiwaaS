# Private Worker (My Machines) — KashiwaaS production

KashiwaaS Bot launches Cursor Cloud Agents on a **self-hosted machine** (Remote Control / My Machines), not on Cursor-hosted cloud VMs or team pools.

## Production selection (TAK-132)

| Setting | Value | Notes |
|---------|-------|-------|
| `CURSOR_ENV_TYPE` | `machine` | Remote Control / My Machines |
| `CURSOR_ENV_NAME` | `<machine-env.name>` | Value for `POST /v1/agents` → `env.name` — **not** the dashboard display string from `v0/private-workers` |
| `CURSOR_LAUNCH_MODE` | `env_only` | ubuntu24 worker has **no repo** checkout |
| Chat platform | Slack | Mattermost is out of scope for production cutover |

### Launch policy

- **Adopt `machine`:** Single ubuntu24 VM already runs Remote Control; matches KashiwaaS ops (same host as Bot target).
- **Do not use `pool`:** No team pool worker is provisioned; Service Account keys are unnecessary for `machine`.
- **Do not use `cloud`:** Cursor-hosted VMs are the legacy path being replaced (TAK-137 production cutover runbook).

## Resolve worker names (required before cutover)

Re-fetch before changing production values.

### 1. List connected workers (`GET /v0/private-workers`)

The public API returns **flat** worker objects (no `labels[]`, no internal `cursor-agent-worker-…` field):

```bash
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v0/private-workers?status=all&limit=50" \
  | jq '.workers[] | {
      workerId,
      display_name: .name,
      workspaceRootPath,
      repoOwner,
      repoName,
      isInUse
    }'
```

Example shape (do not commit live IDs):

```json
{
  "workerId": "<uuid>",
  "display_name": "~/ghq/github.com/takak2166 @ ubuntu24",
  "workspaceRootPath": "/home/ubuntu/ghq/github.com/takak2166",
  "repoOwner": "",
  "repoName": "",
  "isInUse": false
}
```

Use **`display_name`** or **`workspaceRootPath`** to pick the ubuntu24 production row. The JSON field **`name`** in this response is the UI label only.

### 2. Set `CURSOR_ENV_NAME` (`env.name` for the API)

Bot payloads and `POST /v1/agents` need the **`env.name`** string (often `cursor-agent-worker-…`). That value is **not** present on the flat `v0/private-workers` response above, so jq filters like `.labels[] | select(.key=="name")` will not match anything.

**Recommended:** copy from recent agents that ran on your machine:

```bash
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v1/agents?limit=20" \
  | jq '.items[] | select(.env.type == "machine") | {id, status, env}'
```

Set `CURSOR_ENV_NAME` to the **`env.name`** you see for runs that used your ubuntu24 worker (same value the dashboard used when those agents were created).

If you have no history yet, start one agent from the Cursor UI on that machine (no-repo / My Machines), then re-run the query above.

### Example worker record

Example shape after resolving (do **not** commit live values):

```yaml
cursor_env:
  type: machine
  display_name: "~/ghq/github.com/takak2166 @ ubuntu24"   # v0 .name — humans / dashboard
  name: cursor-agent-worker-xxxxxxxxxx                      # v1 env.name → CURSOR_ENV_NAME
  worker_id: "<uuid from v0 workerId>"
  workspace: /home/ubuntu/ghq/github.com/takak2166          # v0 workspaceRootPath
  repos: []                                                 # empty repoOwner/repoName on v0
  machine: ubuntu24
```

### Display name vs API `env.name`

| Source | Field | Example role |
|--------|-------|----------------|
| `GET /v0/private-workers` | `.name` | Dashboard display — **do not** use as `CURSOR_ENV_NAME` |
| `GET /v1/agents` | `.env.name` | Bot / API — **set `CURSOR_ENV_NAME` to this** |
| Slack / UI `worker=` | display string | Same as v0 `.name` |

## Worker lifecycle

### Restart policy

ubuntu24 worker is connected via **Cursor Remote Control** (IDE / CLI outbound connection). We do **not** run a separate systemd unit for the Worker process in this phase.

| Event | Expected behavior |
|-------|-------------------|
| Cursor IDE / Remote session active | Worker shows **connected** in `GET /v0/private-workers` |
| OS reboot | Reconnect Cursor Remote on ubuntu24 (same flow as initial setup) |
| Worker disconnected | Open Cursor on ubuntu24 → verify machine appears under My Machines → reconnect |

**Decision:** Use **Cursor Remote reconnect** after reboot rather than deploying a dedicated systemd unit for `agent worker start`, until unattended worker startup is required.

### Health check (after reboot or incident)

```bash
: "${CURSOR_ENV_NAME:?Set CURSOR_ENV_NAME}"

# 1. Worker connected? (match by workspace — v0 has no env.name)
WORKSPACE="/home/ubuntu/ghq/github.com/takak2166"
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v0/private-workers?status=all&limit=50" \
  | jq --arg ws "$WORKSPACE" '.workers[] | select(.workspaceRootPath == $ws)'

# 2. env.name still valid for API? (optional: recent machine agents)
curl -u "$CURSOR_API_KEY:" "https://api.cursor.com/v1/agents?limit=10" \
  | jq --arg n "$CURSOR_ENV_NAME" '.items[] | select(.env.name == $n) | {id, status, env}'
```

Pass criteria: primary worker row present for your `workspaceRootPath`, empty `repoOwner` / `repoName` (no-repo). For cutover, at least one recent agent should show the same `env.name` as `CURSOR_ENV_NAME`.

## Related docs

- [cursor-secrets.md](cursor-secrets.md) — API key type, host placement, 403 triage
- [runtime-config.md](runtime-config.md) — environment variables
- [bot.md](bot.md) — Slack Bot operation
- [private-worker-e2e.md](private-worker-e2e.md) — curl + Slack E2E

## References

- [My Machines](https://cursor.com/docs/cloud-agent/my-machines)
- [Self-Hosted Machines](https://cursor.com/docs/cloud-agent/self-hosted-guides/my-machines)
- [Cloud Agents API v1](https://cursor.com/docs/cloud-agent/api/endpoints)
