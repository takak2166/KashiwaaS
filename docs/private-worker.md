# Private Worker (My Machines) — KashiwaaS production

KashiwaaS Bot launches Cursor Cloud Agents on a **self-hosted machine** (Remote Control / My Machines), not on Cursor-hosted cloud VMs or team pools.

## Production selection (TAK-132)

| Setting | Value | Notes |
|---------|-------|-------|
| `CURSOR_ENV_TYPE` | `machine` | Remote Control / My Machines |
| `CURSOR_ENV_NAME` | `cursor-agent-worker-676f7f7b4d` | API internal label — **not** the UI display name |
| `CURSOR_LAUNCH_MODE` | `env_only` | ubuntu24 worker has **no repo** checkout |
| Chat platform | Slack | Mattermost is out of scope for production cutover |

### Launch policy

- **Adopt `machine`:** Single ubuntu24 VM already runs Remote Control; matches KashiwaaS ops (same host as Bot target).
- **Do not use `pool`:** No team pool worker is provisioned; Service Account keys are unnecessary for `machine`.
- **Do not use `cloud`:** Cursor-hosted VMs are the legacy path being replaced (see [production-cutover-runbook.md](production-cutover-runbook.md)).

## Observed workers (2026-09-06)

Re-fetch before changing production values:

```bash
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v0/private-workers?status=all&limit=50"
```

Existing agents' `env` field:

```bash
curl -u "$CURSOR_API_KEY:" \
  "https://api.cursor.com/v1/agents?limit=5"
```

### Primary (KashiwaaS production target)

```yaml
cursor_env:
  type: machine
  display_name: "~/ghq/github.com/takak2166 @ ubuntu24"
  name: cursor-agent-worker-676f7f7b4d          # POST /v1/agents env.name
  worker_id: 93d48c71-7abb-5e07-a280-20427d5e31f5
  workspace: /home/ubuntu/ghq/github.com/takak2166
  repos: []                                       # no-repo worker
  machine: ubuntu24
```

### Other connected workers (not production)

| Display name | API `env.name` | Repos | Note |
|--------------|----------------|-------|------|
| `~/quoridor @ ubuntu24` | `cursor-agent-worker-b57646a2d0` | `takak2166/quoridor` | Different project |
| `~/ghq/github.com/takak2166/KashiwaaS @ LAPTOP-L6L2UE39` | `cursor-agent-worker-f2d0ff614f` | `takak2166/KashiwaaS` | WSL laptop; not ubuntu24 prod |

### Display name vs API `env.name`

| UI / Slack `worker=` | Bot `CURSOR_ENV_NAME` |
|----------------------|------------------------|
| `~/ghq/github.com/takak2166 @ ubuntu24` | `cursor-agent-worker-676f7f7b4d` |

The Bot and API payloads **must** use the internal `name` label. The display name is for humans and the Cursor dashboard only.

## Related docs

- [runtime-config.md](runtime-config.md) — environment variables
- [bot.md](bot.md) — Slack Bot operation
- [production-cutover-runbook.md](production-cutover-runbook.md) — cutover / rollback (TAK-137)
- [private-worker-e2e.md](private-worker-e2e.md) — curl + Slack E2E (TAK-136)

## References

- [My Machines](https://cursor.com/docs/cloud-agent/my-machines)
- [Self-Hosted Machines](https://cursor.com/docs/cloud-agent/self-hosted-guides/my-machines)
- [Cloud Agents API v1](https://cursor.com/docs/cloud-agent/api/endpoints)
