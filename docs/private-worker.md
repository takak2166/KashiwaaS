# Private Worker (My Machines) — KashiwaaS production

KashiwaaS Bot launches Cursor Cloud Agents on a **self-hosted machine** (Remote Control / My Machines), not on Cursor-hosted cloud VMs or team pools.

## Production selection (TAK-132)

| Setting | Value | Notes |
|---------|-------|-------|
| `CURSOR_ENV_TYPE` | `machine` | Remote Control / My Machines |
| `CURSOR_ENV_NAME` | `<your-machine-env-name>` | API internal label — **not** the UI display name; resolve via curl below |
| `CURSOR_LAUNCH_MODE` | `env_only` | ubuntu24 worker has **no repo** checkout |
| Chat platform | Slack | Mattermost is out of scope for production cutover |

### Launch policy

- **Adopt `machine`:** Single ubuntu24 VM already runs Remote Control; matches KashiwaaS ops (same host as Bot target).
- **Do not use `pool`:** No team pool worker is provisioned; Service Account keys are unnecessary for `machine`.
- **Do not use `cloud`:** Cursor-hosted VMs are the legacy path being replaced (TAK-137 production cutover runbook).

## Resolve worker names (required before cutover)

Re-fetch before changing production values:

```bash
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v0/private-workers?status=all&limit=50" \
  | jq '.workers[] | {display_name, env_name: (.labels[] | select(.key=="name") | .value), worker_id: .id, repos}'
```

Pick the row for your ubuntu24 production machine. Set `CURSOR_ENV_NAME` to the **`env_name`** value (internal API label), not the UI display name.

Existing agents' `env` field:

```bash
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v1/agents?limit=5"
```

### Example worker record

Example shape after resolving via curl (do **not** commit live values):

```yaml
cursor_env:
  type: machine
  display_name: "~/ghq/github.com/takak2166 @ ubuntu24"   # UI label — example only
  name: <your-machine-env-name>                            # POST /v1/agents env.name → CURSOR_ENV_NAME
  worker_id: <your-worker-id>
  workspace: /home/ubuntu/ghq/github.com/takak2166
  repos: []                                                # no-repo worker
  machine: ubuntu24
```

### Display name vs API `env.name`

| UI / Slack `worker=` | Bot `CURSOR_ENV_NAME` |
|----------------------|------------------------|
| `~/ghq/github.com/takak2166 @ ubuntu24` | `<your-machine-env-name>` (from curl) |

The Bot and API payloads **must** use the internal `name` label. The display name is for humans and the Cursor dashboard only.

## Related docs

- [cursor-secrets.md](cursor-secrets.md) — API key type, host placement, 403 triage
- [runtime-config.md](runtime-config.md) — environment variables
- [bot.md](bot.md) — Slack Bot operation

## References

- [My Machines](https://cursor.com/docs/cloud-agent/my-machines)
- [Self-Hosted Machines](https://cursor.com/docs/cloud-agent/self-hosted-guides/my-machines)
- [Cloud Agents API v1](https://cursor.com/docs/cloud-agent/api/endpoints)
